#!/usr/bin/env python3
"""Slider page for live strip colour tuning (live control tokens, docs/configuration.md).

    python3 calibration/knobs.py --ssh USER@HOST --file /path/to/control.txt [--docker CONTAINER] [--port 8795]

Listens on 127.0.0.1 only. Each change writes "run,<tokens>" to the control file the app polls (over ssh,
optionally inside a docker container); after 2 s idle the file goes back to exactly "run".
Pair it with calibration/mkcard.py test cards on a PC input."""
import argparse, http.server, json, subprocess, threading, urllib.parse

ap = argparse.ArgumentParser()
ap.add_argument("--ssh", required=True); ap.add_argument("--file", required=True)
ap.add_argument("--docker", default=""); ap.add_argument("--port", type=int, default=8795)
A = ap.parse_args()
KNOBS = [  # token, label, min, max, step, value
    ("wtr", "white LED: remove red", -1, 1, 0.02, 0.2),
    ("wtg", "white LED: remove green (neg = add)", -1, 1, 0.02, -0.1),
    ("wtb", "white LED: add blue", -1, 1, 0.02, 0.8),
    ("wm", "share of white on white LED", 0, 1, 0.05, 1.0),
    ("wgn", "white LED brightness vs RGB white", 0.2, 4, 0.05, 1.0),
    ("gamma", "brightness curve (higher = brighter)", 0.3, 2, 0.05, 0.6),
    ("xg", "green in mixed colours", 0.2, 2, 0.02, 0.9),
    ("xb", "blue in mixed colours", 0.2, 2, 0.02, 0.75),
    ("gx", "red added to green", 0, 1, 0.02, 0.25),
    ("dd", "dark colour desaturation", 0, 1, 0.05, 0.4),
    ("cg", "chroma gamma", 1, 3, 0.05, 2.2),
]
lock = threading.Lock()
timer = None

def write(body):
    cmd = f"printf '{body}' > {A.file}"
    if A.docker: cmd = f"docker exec {A.docker} sh -c \"{cmd}\""
    subprocess.run(["ssh", A.ssh, cmd], timeout=15)

def restore():
    with lock:
        write("run")

PAGE = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width">
<title>Ambilight knobs</title><style>
body{font:15px system-ui;background:#1b1b1b;color:#eee;max-width:640px;margin:20px auto;padding:0 16px}
.k{display:grid;grid-template-columns:1fr 70px;gap:4px 10px;margin:12px 0}input{grid-column:1/3;width:100%}
code{background:#333;padding:6px;display:block;white-space:pre-wrap;margin-top:16px}small{color:#999}</style>
<h2>Ambilight knobs</h2><small>Changes reach the strip in about 1 s. Send me the line at the bottom when happy.</small>
<div id=k></div><code id=out></code><script>
const K=__KNOBS__;let t=null;const v={};
const root=document.getElementById('k');
for(const [tok,label,mn,mx,st,val] of K){v[tok]=val;
 const d=document.createElement('div');d.className='k';
 d.innerHTML=`<label>${label} <small>(${tok})</small></label><b id=v_${tok}>${val}</b><input type=range min=${mn} max=${mx} step=${st} value=${val}>`;
 d.querySelector('input').oninput=e=>{v[tok]=+e.target.value;document.getElementById('v_'+tok).textContent=e.target.value;show();clearTimeout(t);t=setTimeout(send,250)};
 root.appendChild(d)}
function line(){return Object.entries(v).map(([a,b])=>a+'='+b).join(',')}
function show(){document.getElementById('out').textContent=line()}
function send(){fetch('/set?t='+encodeURIComponent(line()))}
show();</script>"""

class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        global timer
        u = urllib.parse.urlparse(self.path)
        if u.path == "/set":
            toks = urllib.parse.parse_qs(u.query).get("t", [""])[0]
            ok = all(c.isalnum() or c in "=,.-" for c in toks)
            if ok:
                with lock:
                    write("run," + toks)
                    if timer: timer.cancel()
                    timer = threading.Timer(2.0, restore); timer.start()
            self.send_response(200 if ok else 400); self.end_headers(); return
        body = PAGE.replace("__KNOBS__", json.dumps(KNOBS)).encode()
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
        self.wfile.write(body)

print("open http://127.0.0.1:%d/" % A.port, flush=True)
http.server.ThreadingHTTPServer(("127.0.0.1", A.port), H).serve_forever()
