import json,re,sys
since=sys.argv[2]
for line in open(sys.argv[1],"rb"):
    try: d=json.loads(line)
    except Exception: continue
    if "ppi" not in d or "raw10_sample" not in d["ppi"]: continue
    t=d["ts_utc"][11:19]
    if t<since: continue
    v=[tuple(map(int,re.search(r"=(\d+),(\d+),(\d+)",x).groups())) for x in d["ppi"]["raw10_sample"]]
    nz=[x for x in v if max(x)>0]
    m=sorted(nz)[len(nz)//2] if nz else (0,0,0)
    print(t,m,len(nz))
