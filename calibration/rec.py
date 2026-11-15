import json, re, sys, time, os
src=sys.argv[1]; out=sys.argv[2]; last=None
while True:
    try:
        d=json.load(open(src))
        if d["ts_utc"]!=last:
            last=d["ts_utc"]
            v=[tuple(map(int,re.search(r"=(\d+),(\d+),(\d+)",x).groups())) for x in d["ppi"]["raw10_sample"]]
            with open(out,"a") as f: f.write(json.dumps({"t":last[11:19],"v":v})+"\n")
    except Exception as e: pass
    time.sleep(0.5)
