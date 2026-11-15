# TizenAmbilight on a Samsung S90C: findings

Notes from getting [TizenAmbilight](https://github.com/RitwickVerma/TizenAmbilight) running on a 2023
Samsung S90C (Tizen 8.0), on 2026-10-25. Upstream supports only a 2025 S84F (Tizen 9). This file records
what works, what is blocked and why, the measurements behind the colour calibration, and the open leads
for better capture.

**Status:** working, using the TV's built-in colour measurement ("Hue Sync" API, `ve_*`), 12 spots,
calibrated for the TV's own Jellyfin app (SDR and HDR10). Full-frame capture is blocked by firmware.

---

## 1. The hardware

| | |
|---|---|
| TV | QE77S90CATXXH (S90C, 77", OLED, 2023), firmware below |
| Firmware | Tizen **8.0.0** (`/etc/tizen-release`: `T-PTMCDEUC-0080-REL-202506210102`), kernel 5.4.77, **32-bit ARM** |
| Video backend | `FRC-[PONTUS][120Hz][HW:04] DIMMING-[GLOBAL][00]` (from `ve_get_backend_info`) |
| App identity | uid 5001, SMACK label `User::Pkg::dev.ritwickverma.TizenAmbilight` |
| Signing | Apps2Samsung partner certificate (`VD DEVELOPER Partner CA Class`), made with the Apps2Samsung desktop app |
| WLED | `<wled-ip>`, WLED 0.14.3, ESP, 224 × SK6812 **RGBW** (bus type 30, GRB order), 6 A limiter |
| PC | `<pc-ip>`, KDE Wayland. The TV is also the PC's second screen (`HDMI-A-1`, 1920×1080, HDR + WCG on) |
| Jellyfin | server on the LAN (linuxserver container) |

### LED layout (from the old Hyperion config on the Windows drive)

Source: `Users/<user>/.hyperion/db/hyperion.db`, table `settings`, rows `leds`, `ledConfig` and `device`.

- 224 LEDs, **clockwise** seen from the front. A gap of 88 LEDs at the bottom centre for the stand.
- LED 0 is just left of the gap. Order: bottom-left 7 → left 55 (up) → top 100 → right 55 (down) → bottom-right 7.
- TizenAmbilight assumes a full ring with no gaps. Trick: compute **311 zones** for an imaginary full ring
  (its 16:9 split: top 100, right 56, bottom 99, left 56), send only 224 LEDs, and rotate with
  **`mapOffset` 249**. The 87 zones that no LED uses fall exactly in the stand gap. Found by brute-force
  fit (zone counts 290–330 × all offsets) against the Hyperion LED rectangles. Worst error is about 3 zones,
  at the corners where Hyperion left space empty. Confirmed visually as accurate.

---

## 2. Capture paths investigated

### 2.1 Full-frame video plane (`secvideo_api_capture_video_main`): blocked

- `libvideo-capture.so.0` loads and the symbol resolves (`captureApi=ok`), but every call returns
  **`rc=-95`** (EOPNOTSUPP) with or without video playing (home screen, Jellyfin). Same for every
  `color_format` 0–5.
- Cause: `libvideo-capture.so` is only a thin wrapper. At runtime it `dlopen`s
  **`/prd/usr/lib/libvideo-capture-impl-sec.so`** (string in the binary). If that load fails, every API
  returns `"%s Non implemented Function, Returning Error"`, which is the `-95`.
- `libvideo-capture-impl-sec.so` needs **`libtzcapturec.so`** ("TZ" = TrustZone), and the app may not
  open that file:
  - `dlopen /usr/lib/libtzcapturec.so: Operation not permitted` (EPERM)
  - `File.OpenRead: Access to the path is denied`
  - Its SMACK label is `_` (floor, readable by everyone under SMACK), so **SMACK is not the blocker**.
    EPERM rather than EACCES points to another kernel protection (Samsung LSM or path-based library
    protection), not Unix permissions.
  - `/dev/tzdev`, `/dev/tzdev_invoke`, `/dev/tzrsrc` and `/dev/tzlog` are also denied; `/dev/tzmem` opens.
- **Privileges tried, no effect:** `http://tizen.org/privilege/tee.client` (partner level; it did add the
  app to group **10013**) and `http://developer.samsung.com/privilege/contentanalysis` (public). The
  library still fails with EPERM.
- Same symptom as upstream issue #2 (2021 QN90A). Upstream issue #1 (2025 Q7F) suggests the same lock
  exists on newer models unless the app is signed partner, yet partner signing alone did not unlock it here.
- **Conclusion:** short of root, no sideloaded app gets full-frame capture on this firmware.

### 2.2 Screenshot API (`dc_request_capture_to_file_sync`, `libdisplay-capture-api`): blocked

Returns `rc=1` ("no frame, ret_path empty") permanently. It links `libvideo-capture.so.0`, so it has the
same dependency on the blocked implementation.

### 2.3 Colour measurement / "Hue Sync" API (`libvideoenhance`): **working, in use**

- Tizen 9 firmware exports `ppi_ve_*`, which is all upstream looks for. **Tizen 8 exports `ve_*`**, and
  Tizen 6 and older are said to use `cs_ve_*`. The signatures are identical (confirmed from the C++ names:
  `IVideoEnhancer::get_rgb_measure_condition(VEPPIRgbMeasureInfo_t*)`,
  `set_rgb_measure_position(int,int,int)`, `get_rgb_measure_pixel(int, VEPPIRgbMeasure_t*)`).
  Patched `PpiCapture.cs` to try all three name sets.
- Condition reported by the TV: **2 slots**, 16×16 px block, 20 ms settle, measure space **3840×2160**.
- Throughput: **about 77–97 samples/s** in total. Per-spot refresh = throughput / spots:
  24 spots ≈ 3.3 Hz, **12 spots ≈ 6.4 Hz** (chosen), 8 spots ≈ 10 Hz.
- Each spot measures a 16×16 block of a 4K frame, i.e. a point sample, not an area average.
- Freshness test (`pfresh=2`) **not completed**: "insufficient contrast A=66 B=116 (need >=150)". Needs a
  high-contrast picture to run. On the S84F, 17 ms settle still read fresh (≈ +15% rate).

### 2.4 Other capture-related libraries on the TV (unexplored)

| Library | Notes |
|---|---|
| `libcapi-rm-video-capture.so.0.0.1` | **Most promising lead.** Opens `/dev/video30` and `/dev/dri/card0` directly; does **not** link `libvideo-capture`. Exports `rm_video_capture_open_sdp_hen`, `subscribe_stream`, `set_stream_on/off`, `set_encode_size`, `set_framerate`, `set_bitrate`, `deqevent`, `drm_set_drm_to_encode`. Looks like the hardware-encoder (screen mirroring) path. **`/dev/video10–63` all open for the app** (SMACK `*`). |
| `libscaler-client.so.0` / `libds-tizen-scaler.so.0` | Wayland "tizen scaler" protocol client/server. May give a downscaled composited frame; the video plane may be excluded (it's a hardware overlay). |
| `libep-common-screencapture.so` | Links `libvideo-capture`; `dlopen` fails (undefined symbol `ep_fileutil::CreateDirectory`). |
| `libkeystone-ppi.so.0.1`, `libppi_wrapper.so`, `libppi-acm-core-acmd.so.0.1` | Other picture-processor ("PPI") interfaces, not examined. |
| `/prd/usr/lib/libvideo-capture-impl-sec.so.0.1.0` | **Readable by the app** (not yet pulled). Disassembling it would show exactly how it uses `libtzcapturec`, and whether any part works without it. |
| `Tizen.TV.System.ContentAnalysis.dll` | Samsung's .NET wrapper (`HwCaptureControl`, `IsSupportHWCapture`). Checks `contentanalysis` / `internal/default/platform` in managed code only, then uses `libcapi-video-capture`, so it hits the same block. |

Copies of these binaries (except the impl-sec library) are in `calibration/tv-libs/` (gitignored).

### 2.5 Detecting HDR or SDR input: not found yet

- `ve_get_color_space_info_status`, `ve_get_pc_mode`, `ve_get_dynamic_brightness_mode` and
  `ve_get_histo_value` all return `rc=0`, value 0, whether the HDMI input is HDR or SDR.
- The settings store (vconf) is not reachable as files (`/run/memory` and `/opt/var/kdb` don't exist on
  Tizen 8; it goes through a system service), so reading it needs `libvconf` and exact key names.

---

## 3. What the measurement API reports (important for calibration)

The `ve_*` values (10-bit, 0–1023) are the **TV's internal signal, not display colour**. Their scale and
colour balance **depend on the source**:

| Source | White (R,G,B) | Grey 50% | Red | Notes |
|---|---|---|---|---|
| PC over HDMI, **HDR** on | 445, 462, 461 | 212, 220, 220 | 406, 128, 54 | ≈ linear in sRGB code value; primaries pale, BT.2020-in-PQ-like |
| PC over HDMI, **SDR** | 890, 928, 922 | 534, 555, 553 | 832, 203, 0 | 2× scale, non-linear midtones |
| **Jellyfin app, SDR** (H.264 BT.709) | 986, 994, 838 | 469, 473, 399 | 827, 255, 112 | warm white (blue low) |
| **Jellyfin app, HDR10** (HEVC PQ, 203-nit white) | 690, 695, 586 | 462, 465, 392 | 571, 171, 63 | ≈ 0.6–0.7 × Jellyfin SDR, same colour balance |

Full patch tables: `calibration/data/` and in `calibration/fitj.py` / `fitm2.py`.

Consequences:

- **Within the Jellyfin app, SDR and HDR differ mainly by a brightness factor**, so one calibration that
  ignores overall brightness (see below) covers both. HDR comes out about 30% dimmer, which is acceptable.
- **The PC's HDMI input is a different domain.** The Jellyfin calibration over-brightens it (greys, salmon
  and brown turn white or yellow). Supporting both needs per-source calibrations plus source detection.
- A textbook HDR decode (PQ → BT.2020 → 709) fixed the primaries on HDMI-HDR but crushed midtones and
  tinted whites cyan. **An empirical fit beat the standard maths.**

### Calibration model in use

Root-polynomial colour correction (Finlayson et al.). Features on white-normalised input:
`r, g, b, √(rg), √(gb), √(rb)`, giving 18 coefficients plus the white reference. It scales with
brightness, which is why one fit works for SDR and HDR. Fitted with `calibration/fitj.py` on the Jellyfin
SDR and HDR10 runs together: **RMS error ≈ 11/255** (white 249,255,255; SDR salmon 255,115,102 for
250,128,114; HDR peach 182,132,98 for 178,134,112).

Stored in `TizenAmbilight/config.json` as `ppiCal` (21 numbers: white R,G,B, then 3 rows of 6):

```
986,994,838,-0.28505,-2.76982,0.05827,4.1143,-0.2405,0.09987,-0.88135,0.29173,-0.32897,1.62928,0.41442,-0.11464,-0.06871,-0.80847,0.68459,-0.08461,1.14391,0.14295
```

Applied in `PpiCapture.Snapshot` before interpolation. `ppiCalOn: 0` or the live token `pcal=0` turns it off.

### Other tuning that mattered

- Upstream's tone settings are tuned for the video plane and **shift Hue Sync colours toward blue**:
  `black=12` cuts the weaker channel proportionally harder, and adaptive gamma ≈1.5 grows the dominant
  channel. Final values: `black 0`, `adaptiveGamma 0`, `gamma 1.0`, `saturation 1.0`.
- `alpha 0.5` (lighter smoothing) and `ppiZones 12` for action scenes.
- **Dark scenes (2026-11-12): `gamma 0.6`.** The measured values are gamma-encoded signal, and WLED
  has realtime gamma correction off (`if.live.no-gc: true`), so `gamma 1.0` drove the LEDs linearly
  from code values: 50% grey gave 50% LED light where the screen shows about 20%, and dark scenes were
  far too bright. Gamma < 1 is now allowed (0.25–4; `out = in^(1/gamma)`): 0.6 puts 50% grey at about
  31%, 0.45 would match the screen. The tone map scales R, G and B by one factor taken from the
  **brightest channel** (was luma, which crushed saturated blues and reds once the curve darkens).
  WLED's own realtime gamma is per channel (2.8) and would pull pale colours toward saturated ones,
  undoing the calibration, so it stays off.
- **Scene cuts (2026-11-12): per-zone snap.** Upstream picks the fast alpha (`alphaFast 0.75`) only
  when the mean delta over all zones exceeds `alphaCut 18`. The rolling sampler re-measures two spots
  per frame, so that mean never crosses the cut and cuts were always smoothed. The sampler path now
  decides per zone (`ZoneColors.SmoothTowardsPerZone`): each zone snaps as soon as its spot is
  re-measured after a jump. Remaining delay is mostly the spot refresh (12 spots ≈ 6.4 Hz each).
- WLED **auto-white "Brighter"** (adds W on top of RGB) gives near-neutral whites on this strip.
  "Accurate" (W only) is too yellow (warm-white LED about 3000K); "None" (W unused) is bluish.
  WLED's "white balance correction" (`cr`) is untested and may not apply to realtime data.

---

## 4. Ideas for better capture, most promising first

1. **Hardware-encoder path (`libcapi-rm-video-capture`, `/dev/video30`).** The only full-frame candidate
   that doesn't go through `libvideo-capture`, and its device nodes open for the app. Steps: V4L2
   `VIDIOC_QUERYCAP` / `ENUM_FMT` on `/dev/video10–63` to see whether any node offers raw NV12/YUV output
   of the screen; disassemble `libcapi-rm-video-capture` for the `open_sdp_hen` → `subscribe_stream` call
   order. If it only produces an encoded stream (H.264/HEVC), a tiny resolution (e.g. 64×36) at low
   bitrate could still be decoded in-app. The TV may also block DRM content here
   (`drm_set_drm_to_encode`). Risk: this may be the screen-mirroring path and need a Samsung privilege.
2. **Pull `/prd/usr/lib/libvideo-capture-impl-sec.so.0.1.0`** (readable) and check what it does with
   `libtzcapturec`. If the plane is copied by a normal driver ioctl and TrustZone is only used for
   DRM/protection checks, the ioctl could be called directly.
3. **Faster Hue Sync rate:** finish the freshness test (`pfresh=2` during a high-contrast scene) and lower
   `ppiSettleMs` if 17 ms or less stays fresh (S84F: ≈ +15%). Check whether `libkeystone-ppi` /
   `libppi_wrapper` expose more than 2 slots, or a bigger block for real area averages.
4. **Smarter spot placement:** spend more spots where the picture changes (motion-weighted), or alternate
   coarse full-ring passes with dense passes. Interpolation already fills the zones in between.
5. **Source-aware calibration:** detect the input (HDMI or app) and HDR state through a Tizen API
   (TV window/source info, `libvconf` keys, the local `127.0.0.1:8001` API), then switch calibrations.
   Fallback heuristic: the brightness ceiling of recent readings (HDMI-HDR white ≈ 450, SDR ≈ 900+).
6. **Calibrate with the TV's own picture mode in mind:** the Jellyfin white reads warm (B ≈ 0.85 R) while
   PC HDMI reads neutral, so picture mode or colour temperature probably enters the measurement. Recalibrate
   after changing picture modes.

Root is the only known route past `libtzcapturec` and is out of scope.

---

## 5. How to work on this again

### Build, sign, install

```bash
cd TizenAmbilight   # this repository
dotnet msbuild TizenAmbilight/TizenAmbilight.csproj -restore -t:Rebuild -p:Configuration=Release
# Apps2Samsung CLI v3.0.0-beta (linux-x64 tarball from its GitHub releases), kept in ~/.local/opt/a2scli.
# It reuses the desktop app's partner certificate:
apps2samsung-cli install TizenAmbilight/bin/Release/tizen90/dev.ritwickverma.TizenAmbilight-1.0.0.tpk \
  --tv <tv-ip> --partner --no-launch
apps2samsung-cli launch dev.ritwickverma.TizenAmbilight --tv <tv-ip>   # or cold-boot the TV
```

`config.json` is gitignored. It is bundled into the package at build time, so edit it and rebuild.

### Diagnostics workflow

- Add `"probeEndpoint": "http://<pc-ip>:8791"` and `"controlUrl": "http://<pc-ip>:8792/control"`
  to `config.json`, and open ufw for 8791–8792 from the LAN.
- `calibration/diag-receiver.py <outdir>`: accepts telemetry (`latest.json`, `history.log`) and any file
  upload. Upstream's `tools/stats-receiver.py` only accepts two file names.
- `tools/control-server.py --file <f>`: write comma-separated tokens to `<f>` (e.g. `run,backend=2,pz=12`).
  Useful tokens: `backend=0|2`, `pz`, `psleep`, `pfresh`, `ppigrid=1`, `alpha`, `sat`, `gamma`, `black`,
  `ag`, `pcal`, `pause` / `run`.
- `calibration/Diag.cs.keep`: the device-diagnostics module (library scan with `dlerror`, SMACK xattrs,
  `/dev` access, `/proc/self/status` groups, privilege/policy file upload, `ve_*` state monitor). To use it,
  copy it to `TizenAmbilight/src/Diag.cs` and call `Diag.Start(cfg.Endpoint);` in `Program.cs` before
  "resolve the capture library".
- `calibration/rec.py` + `timeline.py`: log and print the raw `raw10_sample` per telemetry report.

### Recalibrating colours

1. `calibration/mkvid.sh` (SDR) and `calibration/mkhdr.py` (HDR10, exact PQ values) build 18-patch test
   videos, 8 s per patch. Copy them to the Jellyfin library and play them on the TV.
2. Read the per-patch averages from the telemetry history (`timeline.py`), update the dicts in
   `fitj.py`, refit, and paste the 21 numbers into `ppiCal`.
3. For the PC desktop, show patches with
   `mpv --fs --fs-screen-name=HDMI-A-1 "av://lavfi:color=c=<colour>:s=1920x1080"`.

### Gotchas

- A CLI `launch` shows an "Error, please wait and try again" popup and prints `launch failed[404]`
  (a headless service was "launched" like an app). Both are harmless: the service starts anyway (WLED goes
  live after about 10 s), and pressing OK on the popup or ignoring it makes no difference (checked 2026-11-15).
- The TV is **32-bit ARM**: P/Invoke `ssize_t`/`size_t` as `IntPtr`, not `long` (a `getxattr` binding
  with `long` crashed).
- Send `pause` over the control channel before installing over a running copy (upstream's scaler-wedge
  warning). In my setup the control file is `config/www/ambilight-control.txt` in Home Assistant, served
  by a plain `python -m http.server` container (write it with `docker exec homeassistant sh -c "printf pause > /config/www/..."`).
  Live tuning tokens go in the same file (`run,gamma=0.6`), but HA's TV Ambilight switch reads as off
  unless the file is exactly `run`, so put it back afterwards and check WLED `lor` is 0.
- WLED 16 has no `/json/live` over HTTP (501); use the WebSocket or look at the strip.
- Test patches shown from the PC can have black bars at the sides, so some spots read 0. Average only
  non-zero spots, or use the Jellyfin videos.
- The PC's shell is zsh: `for c in $LIST` does not word-split; run such scripts with bash.
