import subprocess, sys, os
out=sys.argv[1]; work=sys.argv[2]; font=subprocess.check_output(["fc-match","-f","%{file}","sans"]).decode()
P=["black","white","0xbfbfbf","0x808080","0x404040","red","lime","blue","yellow","cyan","magenta","0xfa8072","0xff8000","0x8000ff","0x800080","0x804000","0xffc0a0","black"]
named={"black":0x000000,"white":0xffffff,"red":0xff0000,"lime":0x00ff00,"blue":0x0000ff,"yellow":0xffff00,"cyan":0x00ffff,"magenta":0xff00ff}
def s2l(c): c/=255; return c/12.92 if c<=0.04045 else ((c+0.055)/1.055)**2.4
M=[[0.6274,0.3293,0.0433],[0.0691,0.9195,0.0114],[0.0164,0.0880,0.8956]]  # 709 -> 2020 linear
m1,m2,c1,c2,c3=2610/16384,2523/4096*128,3424/4096,2413/4096*32,2392/4096*32
def pq(nits):
    y=max(nits,0)/10000; return ((c1+c2*y**m1)/(1+c3*y**m1))**m2
segs=[]
for i,name in enumerate(P):
    v=named.get(name, int(name,16) if name.startswith("0x") else 0)
    rgb=[(v>>16)&255,(v>>8)&255,v&255]
    lin=[s2l(x) for x in rgb]
    l2=[sum(M[r][k]*lin[k] for k in range(3)) for r in range(3)]
    e=[pq(203*x) for x in l2]
    hexc="0x%02x%02x%02x"%tuple(round(255*x) for x in e)  # 8-bit approx for lavfi; precise 10-bit below via geq
    vals=[round(1023*x) for x in e]
    f=os.path.join(work,"hseg_%02d.mkv"%i); segs.append(f)
    # build an rgb48 frame with exact PQ code values (16-bit = 10-bit<<6), label drawn in mid grey
    subprocess.check_call(["ffmpeg","-hide_banner","-loglevel","error","-y","-f","lavfi","-i","color=c=black:s=1920x1080:r=24:d=8",
        "-vf",f"format=gbrp16le,geq=r={vals[0]*64}:g={vals[1]*64}:b={vals[2]*64},drawtext=fontfile={font}:text='{i} {name}':fontsize=36:fontcolor=gray:x=(w-tw)/2:y=(h-th)/2",
        "-c:v","ffv1","-f","matroska",f])
    print(name, rgb, "-> PQ10", vals)
open(os.path.join(work,"hlist.txt"),"w").write("".join(f"file '{s}'\n" for s in segs))
subprocess.check_call(["ffmpeg","-hide_banner","-loglevel","error","-y","-f","concat","-safe","0","-i",os.path.join(work,"hlist.txt"),
  "-vf","scale=out_color_matrix=bt2020:out_range=tv,format=yuv420p10le",
  "-c:v","libx265","-preset","medium","-crf","10","-tag:v","hvc1",
  "-color_primaries","bt2020","-color_trc","smpte2084","-colorspace","bt2020nc","-color_range","tv",
  "-x265-params","log-level=error:colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc:range=limited:hdr10=1:master-display=G(13250,34500)B(7500,3000)R(34000,16000)WP(15635,16450)L(10000000,50):max-cll=1000,400",
  out])
