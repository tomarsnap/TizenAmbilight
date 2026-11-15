#!/usr/bin/env python3
"""Build edge test cards for judging the strip by eye: colour blocks along the top, right and left
edges (where a typical strip runs), labelled, on a dark grey field. Needs ffmpeg.

    python3 calibration/mkcard.py colours out.png      # browns, skin, orange, olive, yellow, lime, cyan, ...
    python3 calibration/mkcard.py whites out.png       # white, greys, pastels (white-LED tint)
    mpv --fs --fs-screen-name=<output> --image-display-duration=inf out.png

Turn the stale-picture fade off while judging (token stale=0): a still card dims to staleLevel after
staleMs, which looks like a colour error."""
import subprocess, sys

CARDS = {
    "colours": ["402010 dark brown", "e0a080 skin", "ff8000 orange", "808000 olive", "ffff00 yellow",
                "00ff00 lime", "00ffff cyan", "fa8072 salmon", "204020 dark green", "804000 brown"],
    "whites": ["ffffff white", "c0c0c0 light grey", "e0a080 skin", "fa8072 salmon", "ffc0a0 peach",
               "808080 grey", "ffc0cb pink", "f5deb3 wheat", "404040 dark grey", "c08060 tan"],
}
# top 4 (left to right), right 3 (top to bottom), left 3 (top to bottom)
SLOTS = [(0, 0, 480, 240), (480, 0, 480, 240), (960, 0, 480, 240), (1440, 0, 480, 240),
         (1440, 240, 480, 280), (1440, 520, 480, 280), (1440, 800, 480, 280),
         (0, 240, 480, 280), (0, 520, 480, 280), (0, 800, 480, 280)]

def main():
    name, out = sys.argv[1], sys.argv[2]
    font = subprocess.run(["fc-match", "-f", "%{file}", "sans"], capture_output=True, text=True).stdout
    f = []
    for i, ((x, y, w, h), item) in enumerate(zip(SLOTS, CARDS[name])):
        c, label = item.split(" ", 1)
        f.append(f"drawbox=x={x}:y={y}:w={w}:h={h}:color=0x{c}:t=fill")
        f.append(f"drawtext=fontfile={font}:text='{i + 1} {label}':fontsize=34:fontcolor=white:"
                 f"borderw=2:bordercolor=black:x={x}+20:y={y}+{h}/2-17")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    "color=c=0x202020:s=1920x1080", "-vf", ",".join(f), "-frames:v", "1", out], check=True)

if __name__ == "__main__":
    main()
