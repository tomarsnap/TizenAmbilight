import base64, json, os, re, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
OUT = sys.argv[1]
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 64 * 1024 * 1024: self.send_response(413); self.end_headers(); return
        raw = self.rfile.read(n)
        try:
            if self.path.startswith("/file"):
                d = json.loads(raw)
                name = re.sub(r"[^A-Za-z0-9._+-]", "_", os.path.basename(d.get("name") or "x"))
                blob = base64.b64decode(d.get("data") or "")
                open(os.path.join(OUT, name), "wb").write(blob)
                print(time.strftime("%H:%M:%S"), "file", name, len(blob), flush=True)
            else:
                open(os.path.join(OUT, "latest.json"), "wb").write(raw)
                open(os.path.join(OUT, "history.log"), "ab").write(raw.replace(b"\n", b" ") + b"\n")
            self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
        except Exception as e:
            self.send_response(400); self.end_headers(); self.wfile.write(str(e).encode())
ThreadingHTTPServer((sys.argv[2] if len(sys.argv) > 2 else "0.0.0.0", 8791), H).serve_forever()
