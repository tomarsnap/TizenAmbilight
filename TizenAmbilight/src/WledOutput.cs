using System;
using System.Net;
using System.Net.Sockets;

namespace TizenAmbilight
{
    /// <summary>
    /// WLED realtime UDP output, DRGB protocol (WLED "UDP realtime" port 21324).
    ///
    /// Packet layout:
    ///     byte 0        0x02          protocol id: DRGB (R,G,B per LED, no separate white channel)
    ///     byte 1        timeout       seconds WLED keeps the strip live after our last packet
    ///     byte 2..      3 bytes/LED   R,G,B for LED 0, R,G,B for LED 1, ...
    ///
    /// 73 LEDs => 2 + 73*3 = 221 bytes. Sent as a single UDP datagram.
    ///
    /// SAFETY: this class never sends anything unless the app asks it to, which it does only when
    /// `outputEnabled` is true AND a `wledIp` is configured. A fresh install sends nothing.
    ///
    /// BLANKING: <see cref="SendBlackout"/> is the deliberate "turn the strip off" packet — the
    /// same DRGB frame with every LED at 0,0,0. While the app wants the strip dark it re-sends this
    /// inside the timeout, because a single blackout expires and WLED reverts to its own colour. The app sends it when capture has failed for a
    /// sustained run (the strip would otherwise sit latched on a stale frame) and from its
    /// terminate callback. A hard kill cannot run that callback, which is why every packet carries
    /// the short timeout rather than relying on the callback alone.
    /// </summary>
    public static class WledOutput
    {
        public const byte ProtocolDrgb = 0x02;
        public const int DefaultPort = 21324;
        public const byte DefaultTimeoutSeconds = 1;

        /// <summary>WLED accepts at most 490 LEDs in one DRGB datagram (2 + 490*3 = 1472 bytes, one
        /// Ethernet MTU of UDP payload). Larger strips would need the DNRGB protocol.</summary>
        public const int MaxDrgbLeds = 490;

        /// <summary>Timeout byte for the stall BLACKOUT packet. Deliberately longer than the normal
        /// frame timeout: the app re-sends every BlackoutHoldMs (1 s), so 4 s means up to three
        /// consecutive lost packets still leave WLED latched to black. At 1 s a single dropped datagram
        /// was enough for WLED to drop live mode and flash its own default ORANGE for the whole stall.</summary>
        public const byte BlackoutTimeoutSeconds = 4;

        static byte[] _mappedScratch;   // per-frame datagram, reused; render thread only

        /// <summary>Build the DRGB datagram for a run of zones, in strip order.</summary>
        public static byte[] BuildDrgb(ZoneColors colors, byte timeoutSeconds)
        {
            if (colors == null) throw new ArgumentNullException("colors");
            byte[] p = new byte[2 + colors.Count * 3];
            p[0] = ProtocolDrgb;
            p[1] = timeoutSeconds;
            int o = 2;
            for (int i = 0; i < colors.Count; i++)
            {
                p[o++] = colors.R[i];
                p[o++] = colors.G[i];
                p[o++] = colors.B[i];
            }
            return p;
        }

        // ---- zone -> LED MAPPING ----
        // The zone colours are computed in FRAME order: top (L->R), right (T->B), bottom (R->L),
        // left (B->T), clockwise from the frame's top-left. Where those land on the PHYSICAL strip
        // depends entirely on which corner the installer started at and which way the strip runs,
        // so both are steerable without a rebuild:
        //     mapOffset  - rotate the ring by this many LEDs (0..count-1)
        //     mapReverse - run the ring the other way
        // With ledCount > zoneCount the extra LEDs are written BLACK, NOT spread proportionally - the
        // mapping stays strictly 1:1 (see the loop below). An earlier version of this comment claimed a
        // proportional spread; that was never what the code did. Proximity-spreading drifts ~2 LEDs by
        // the end of the ring and breaks the corner alignment, which is why it was rejected.
        public static byte[] BuildDrgbMapped(ZoneColors colors, byte timeoutSeconds,
                                             double gain, double gamma, double black,
                                             int mapOffset, bool mapReverse, int ledCount)
        {
            if (colors == null) throw new ArgumentNullException(nameof(colors));
            if (ledCount < 1) ledCount = colors.Count;
            byte[] t = Lut(gain, gamma, black);
            // REUSED BUFFER. This is the per-frame builder (~25x/second) and it allocated a 227-byte
            // array every frame for a packet sent immediately and discarded. Sized EXACTLY rather than
            // ">=": Send() transmits payload.Length bytes, so an oversized buffer would emit extra LEDs.
            // Safe because the render loop sends before the next call and retains nothing.
            bool rgbw = Rgbw;
            int bpl = rgbw ? 4 : 3;
            if (rgbw && ledCount > MaxDrgbwLeds) ledCount = MaxDrgbwLeds;
            int need = 2 + ledCount * bpl;
            if (_mappedScratch == null || _mappedScratch.Length != need) _mappedScratch = new byte[need];
            byte[] p = _mappedScratch;
            p[0] = rgbw ? ProtocolDrgbw : ProtocolDrgb;
            p[1] = timeoutSeconds;

            int zones = colors.Count;
            for (int led = 0; led < ledCount; led++)
            {
                int o = 2 + led * bpl;

                // LEDs past the zone count are written EXPLICITLY BLACK rather than left alone.
                // Leaving them unwritten was the bug: WLED then keeps driving them from its own
                // segment output, which is not ours and showed up as colour on the last LEDs.
                // This also keeps the zone->LED mapping strictly 1:1. A proportional spread across
                // a larger ledCount would drift ~2 LEDs by the end of the ring and break the corners.
                if (led >= zones)
                {
                    p[o] = 0; p[o + 1] = 0; p[o + 2] = 0;
                    if (rgbw) p[o + 3] = 0;
                    continue;
                }

                int i = (mapReverse ? (-led) : led) + mapOffset;
                i %= zones;
                if (i < 0) i += zones;

                // Tone-map through the BRIGHTEST CHANNEL and scale R/G/B by that SAME factor, instead
                // of pushing each channel through the curve independently. A per-channel curve lifts a
                // low channel more than a high one, which compresses their ratio - measured as ~10%
                // relative saturation loss plus a hue shift on real zone colours. Scaling by a common
                // factor changes brightness only, so hue and saturation survive the tone map intact.
                // Max rather than luma: with gamma < 1 (darkening), luma would read a saturated blue
                // (luma 29 of 255) as near-black and crush it, while max keeps it at full scale.
                byte r0 = colors.R[i], g0 = colors.G[i], b0 = colors.B[i];
                int luma = r0 > g0 ? (r0 > b0 ? r0 : b0) : (g0 > b0 ? g0 : b0);
                int nl = t[luma];
                int rr, gg, bb;
                if (luma <= 0)
                {
                    // Neutral: no hue to preserve. (luma 0 means the zone is black or near-black.)
                    rr = gg = bb = nl;
                }
                else if (ChromaGamma != 1.0)
                {
                    // Channel ratios to linear light: the zone colour is gamma-coded (SDR, and the HDR
                    // decode's gamma 2.2 output) but the strip's PWM is linear, so r/max must become
                    // (r/max)^2.2. Keeping the coded ratio showed #ff8000 with green at 50% of red
                    // instead of ~22%: pale, shifted toward yellow/white.
                    float[] rt = RatioLut();
                    float rl = nl * rt[r0 * 1024 / luma], gl = nl * rt[g0 * 1024 / luma], bl = nl * rt[b0 * 1024 / luma];
                    // Strip green is a deep ~520 nm emerald; sRGB green sits near 550 nm. Adding a little
                    // red per unit of CHROMATIC green (above the colour's white part, linear light) pulls
                    // green toward the screen's hue; greys and white stay neutral. It also softens cyan,
                    // which matched the S90C's cyan by eye (2026-11-16; limiting it to green standing alone
                    // made cyan too pure).
                    float wl = rl < gl ? (rl < bl ? rl : bl) : (gl < bl ? gl : bl);
                    float cr = (rl - wl) * ChromaR, cgr = (gl - wl) * ChromaG, cb = (bl - wl) * ChromaB;
                    float fr = wl + cr + GreenToRed * cgr, fg = wl + cgr, fb = wl + cb;
                    // DARK DESATURATION. On screen a dark orange reads as brown because of the brighter
                    // picture around it; a lone dim LED has no such context and shows plain orange. Blend
                    // dark colours toward the grey of equal luminance: fully DarkDesat at black, fading to
                    // none at DarkKnee (output level).
                    if (DarkDesat > 0f && nl < DarkKnee)
                    {
                        float k = DarkDesat * (1f - nl / DarkKnee);
                        float y = 0.2126f * fr + 0.7152f * fg + 0.0722f * fb;
                        fr += k * (y - fr); fg += k * (y - fg); fb += k * (y - fb);
                    }
                    rr = (int)(fr + 0.5f);
                    gg = (int)(fg + 0.5f);
                    bb = (int)(fb + 0.5f);
                }
                else
                {
                    double k = (double)nl / luma;
                    rr = (int)(r0 * k + 0.5); gg = (int)(g0 * k + 0.5); bb = (int)(b0 * k + 0.5);
                }
                if (rr > 255) rr = 255; if (gg > 255) gg = 255; if (bb > 255) bb = 255;
                if (rgbw) EmitRgbw(p, o, rr, gg, bb);
                else { p[o] = (byte)rr; p[o + 1] = (byte)gg; p[o + 2] = (byte)bb; }
            }
            return p;
        }

        // ---- RGBW output (DRGBW, protocol 3) ----
        /// <summary>Send 4 bytes per LED and drive the strip's white LED from the app (config <c>wledRgbw</c>,
        /// token <c>rgbw</c>). Needs WLED's auto-white mode set to "None", otherwise WLED recomputes W.
        /// Why: with WLED's own auto-white the white part of every colour lands on a warm white LED, so
        /// pastels and white came out orange on the reference strip (2026-11-16); here the app decides how
        /// much goes to W and cancels its tint with the RGB LEDs.</summary>
        public static bool Rgbw = false;
        public const byte ProtocolDrgbw = 0x03;
        /// <summary>(1472 - 2) / 4: LEDs in one DRGBW datagram.</summary>
        public const int MaxDrgbwLeds = 367;
        /// <summary>Share of the white part moved to the W LED (token <c>wm</c>, config <c>whiteMix</c>).</summary>
        public static float WhiteMix = 1f;
        /// <summary>W LED output relative to full RGB white at the same value (token <c>wgn</c>, config
        /// <c>whiteGain</c>); W is sent as moved/WhiteGain.</summary>
        public static float WhiteGain = 1f;
        /// <summary>Tint correction per unit of W, in RGB units: positive red removes red, positive blue
        /// adds blue (tokens <c>wtr</c>/<c>wtg</c>/<c>wtb</c>, config <c>whiteTintR/G/B</c>). A warm W LED
        /// needs red &gt; 0 and blue &gt; 0.</summary>
        public static float WhiteTintR = 0.2f, WhiteTintG = -0.1f, WhiteTintB = 0.8f;
        /// <summary>The same correction while the content is HDR (tokens <c>hwtr</c>/<c>hwtg</c>/<c>hwtb</c>,
        /// config <c>hdrWhiteTintR/G/B</c>). The S90C renders white cooler in its HDR picture mode, so the
        /// strip's white needs more blue there to match. <see cref="HdrActive"/> picks the set per frame.</summary>
        public static float HdrWhiteTintR = 0.2f, HdrWhiteTintG = -0.1f, HdrWhiteTintB = 0.8f;
        public static volatile bool HdrActive;

        static void EmitRgbw(byte[] p, int o, int r, int g, int b)
        {
            int m = r < g ? (r < b ? r : b) : (g < b ? g : b);
            float moved = m * WhiteMix;
            bool h = HdrActive;
            float fr = r - moved - (h ? HdrWhiteTintR : WhiteTintR) * moved;
            float fg = g - moved - (h ? HdrWhiteTintG : WhiteTintG) * moved;
            float fb = b - moved + (h ? HdrWhiteTintB : WhiteTintB) * moved;
            float w = WhiteGain > 0.05f ? moved / WhiteGain : moved;
            p[o]     = Byte(fr);
            p[o + 1] = Byte(fg);
            p[o + 2] = Byte(fb);
            p[o + 3] = Byte(w);
        }

        static byte Byte(float v) { return v <= 0f ? (byte)0 : v >= 255f ? (byte)255 : (byte)(v + 0.5f); }

        /// <summary>Exponent applied to each channel's ratio to the brightest channel (config/token
        /// <c>chromaGamma</c> / <c>cg</c>). 1 keeps the gamma-coded ratios (pre-v6-s90c.5 behaviour);
        /// 2.2 converts them to linear light for the strip.</summary>
        public static double ChromaGamma = 2.2;
        /// <summary>Red added per unit of green, in linear light (config <c>greenToRed</c>, token <c>gx</c>).
        /// Only applies with <see cref="ChromaGamma"/> != 1.</summary>
        public static float GreenToRed = 0.25f;
        /// <summary>Gains on each channel's CHROMATIC part (above the colour's white part, linear light):
        /// tokens <c>xr</c>/<c>xg</c>/<c>xb</c>, config <c>chromaGainR/G/B</c>. Unlike white balance they
        /// leave greys and white untouched; they correct the strip primaries' relative strength in mixes
        /// (yellow too green -> lower xg; cyan too blue -> lower xb).</summary>
        public static float ChromaR = 1f, ChromaG = 0.9f, ChromaB = 0.75f;
        /// <summary>Saturation removed at black (token <c>dd</c>, config <c>darkDesat</c>), fading linearly to
        /// none at output level <see cref="DarkKnee"/> (token <c>dk</c>, config <c>darkKnee</c>).</summary>
        public static float DarkDesat = 0.4f, DarkKnee = 160f;
        static float[] _ratioLut; static double _ratioLutG = double.NaN;
        static float[] RatioLut()
        {
            if (_ratioLut != null && _ratioLutG == ChromaGamma) return _ratioLut;
            var t = new float[1025];
            for (int i = 0; i <= 1024; i++) t[i] = (float)Math.Pow(i / 1024.0, ChromaGamma);
            _ratioLut = t; _ratioLutG = ChromaGamma;
            return t;
        }

        // ---- brightness shaping ----
        // A dark scene averages to dark zone colours, and no amount of WLED brightness fixes that,
        // so the curve lives here. Two knobs, applied per channel through a 256-entry LUT so
        // the hot path stays a table lookup:
        //     out = clamp( gain * 255 * (v/255)^(1/gamma) )
        // gamma > 1 lifts mid-tones (the perceptual "brighter" people actually want);
        // gain is a straight multiplier on top.
        static byte[] _lut;
        static double _lutGain = double.NaN, _lutGamma = double.NaN, _lutBlack = double.NaN;

        /// <summary>Tone map, applied per channel. TWO stages, and the order matters:
        ///
        ///   1. BLACK LEVEL + CONTRAST STRETCH. Everything at or below `black` goes to zero, and the
        ///      remainder is stretched back over the full range. This is what removes the "milky"
        ///      haze: without it nothing in the chain ever crushes black, so a gamma lift turns dark
        ///      scenes into dark grey. Crucially this gives deep blacks AND bright highlights rather
        ///      than trading one against the other.
        ///
        ///   2. GAMMA / GAIN on the stretched value, for taste.
        ///
        /// black = 16 is the classic video black level (16/255); the app's default of 12 is tuned for
        /// the PQ-decoded plane (see the `black` note in Config.cs).
        /// </summary>
        static byte[] Lut(double gain, double gamma, double black)
        {
            if (_lut != null && gain == _lutGain && gamma == _lutGamma && black == _lutBlack) return _lut;
            if (gain <= 0) gain = 1.0;
            if (gamma <= 0) gamma = 1.0;
            if (black < 0) black = 0;
            if (black > 200) black = 200;
            double span = 255.0 - black;
            var t = new byte[256];
            for (int v = 0; v < 256; v++)
            {
                double x = v - black;
                if (x <= 0) { t[v] = 0; continue; }
                double n = (x / span);                       // stretch back to 0..1
                x = gain * 255.0 * Math.Pow(n, 1.0 / gamma);
                if (x < 0) x = 0; else if (x > 255) x = 255;
                t[v] = (byte)(x + 0.5);
            }
            _lut = t; _lutGain = gain; _lutGamma = gamma; _lutBlack = black;
            return t;
        }

        /// <summary>Build the all-off DRGB datagram for <paramref name="ledCount"/> LEDs: every
        /// LED 0,0,0. This is the packet that un-latches the strip.</summary>
        public static byte[] BuildBlackout(int ledCount)
        {
            if (ledCount < 1) ledCount = 1;
            byte[] p = new byte[2 + ledCount * 3];
            p[0] = ProtocolDrgb;
            p[1] = BlackoutTimeoutSeconds;
            // bytes 2.. already zero — every LED is R=0,G=0,B=0
            return p;
        }

        /// <summary>Build and send the all-off packet for a strip of <paramref name="ledCount"/>
        /// LEDs. Returns null on success or a short error string; never throws.</summary>
        public static string SendBlackout(string ip, int port, int ledCount)
        {
            return Send(ip, port, BuildBlackout(ledCount));
        }

        static UdpClient _udp;
        static IPAddress _udpAddr;
        static int _udpPort = -1;
        static readonly object _udpLock = new object();

        /// <summary>UDP send. Returns null on success or a short error string; never throws.
        ///
        /// The socket is created ONCE and reused. The original built a UdpClient per call - a socket
        /// create + connect + close ~25 times a second for the entire runtime, which is pure syscall and
        /// GC overhead. Reuse also gives WLED one stable source port instead of a new ephemeral port per
        /// packet, which is what a realtime (live) stream should look like.
        ///
        /// LOCKED because the render loop and the shutdown handler (framework thread) can both send.
        /// A failed send DISCARDS the socket so the next call rebuilds a clean one rather than
        /// repeatedly failing on a broken handle.</summary>
        public static string Send(string ip, int port, byte[] payload)
        {
            try
            {
                IPAddress addr;
                if (!IPAddress.TryParse(ip, out addr))
                    return "bad ip '" + ip + "'";

                lock (_udpLock)
                {
                    if (_udp == null || _udpPort != port || !Equals(_udpAddr, addr))
                    {
                        try { if (_udp != null) _udp.Close(); } catch { }
                        _udp = new UdpClient();
                        _udp.Connect(addr, port);
                        _udpAddr = addr;
                        _udpPort = port;
                    }
                    _udp.Send(payload, payload.Length);
                }
                return null;
            }
            catch (Exception e)
            {
                lock (_udpLock)
                {
                    try { if (_udp != null) _udp.Close(); } catch { }
                    _udp = null; _udpPort = -1;
                }
                return e.GetType().Name + ": " + e.Message;
            }
        }
    }
}
