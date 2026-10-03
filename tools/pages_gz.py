# mimics Cloudflare Pages: clean URLs, 404.html, _headers
import http.server, functools, pathlib, os, gzip, io
D=pathlib.Path("dist")
def hdrs(path):
    out=[]; cur=None
    for l in (D/"_headers").read_text().splitlines():
        if l and not l.startswith(" "): cur=l.strip()
        elif ": " in l and cur:
            pat=cur.rstrip("*")
            if path.startswith(pat): out.append(l.strip().split(": ",1))
    return out
class S(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/api/"):
            body=b'{"ok":true,"days":180,"summary":[],"reports":[]}'
            if "gzip" in self.headers.get("Accept-Encoding",""): body=gzip.compress(body)
            self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(body); return
        return super().do_GET()
    def send_head(self):
        p=self.path.split("?")[0].split("#")[0]
        if p!="/" and not os.path.splitext(p)[1]:
            cand=D/(p.strip("/")+".html")
            if cand.exists(): self.path="/"+p.strip("/")+".html"
            else: self.path="/404.html"; self._nf=True
        return super().send_head()
    def send_response(self,code,msg=None):
        super().send_response(404 if getattr(self,"_nf",False) and code==200 else code,msg)
    def copyfile(self, src, dst):
        data=src.read()
        if "gzip" in self.headers.get("Accept-Encoding",""): data=gzip.compress(data,6)
        dst.write(data)
    def send_header(self,k,v):
        if k=="Content-Length" and "gzip" in self.headers.get("Accept-Encoding",""): return
        super().send_header(k,v)
    def end_headers(self):
        if "gzip" in self.headers.get("Accept-Encoding",""): super().send_header("Content-Encoding","gzip")
        for k,v in hdrs(self.path): self.send_header(k,v)
        super().end_headers()
    def log_message(self,*a): pass
http.server.ThreadingHTTPServer(("127.0.0.1",8767),functools.partial(S,directory="dist")).serve_forever()
