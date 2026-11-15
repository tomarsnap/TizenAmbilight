#!/bin/bash
set -e
cd "$1"
FONT=$(fc-match -f '%{file}' sans)
P="black white 0xbfbfbf 0x808080 0x404040 red lime blue yellow cyan magenta 0xfa8072 0xff8000 0x8000ff 0x800080 0x804000 0xffc0a0 black"
if [ ! -f patches_rgb.mkv ]; then i=0; for c in $P; do
  ffmpeg -hide_banner -loglevel error -y -f lavfi -i "color=c=$c:s=1920x1080:r=24:d=8" -vf "drawtext=fontfile=$FONT:text='$i $c':fontsize=36:fontcolor=gray:x=(w-tw)/2:y=(h-th)/2" -pix_fmt rgb24 -c:v libx264rgb -qp 0 -f matroska seg_$(printf %02d $i).mkv; i=$((i+1)); done
fi; ls seg_*.mkv | sed "s/^/file '/;s/$/'/" > list.txt
ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 -i list.txt -c copy patches_rgb.mkv
ffmpeg -hide_banner -loglevel error -y -i patches_rgb.mkv -vf "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p" -c:v libx264 -crf 12 -preset medium -color_primaries bt709 -color_trc bt709 -colorspace bt709 -color_range tv ~/Downloads/ambilight-test-SDR.mp4
ffmpeg -hide_banner -loglevel error -y -i patches_rgb.mkv -vf "zscale=transferin=iec61966-2-1:primariesin=709:matrixin=input:transfer=linear:npl=203,format=gbrpf32le,zscale=primaries=2020:transfer=smpte2084:matrix=2020_ncl:range=limited:npl=10000,format=yuv420p10le" -c:v libx265 -preset medium -crf 12 -tag:v hvc1 -x265-params "log-level=error:colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc:range=limited:hdr10=1:master-display=G(13250,34500)B(7500,3000)R(34000,16000)WP(15635,16450)L(10000000,50):max-cll=1000,400" ~/Downloads/ambilight-test-HDR10.mp4
