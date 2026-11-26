"""Black-box HTTP check of every trace prefix and the address-only compact history."""
import json
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError
from urllib.request import urlopen
from extension import Handler,serve

def main():
    tested=0
    with ThreadingHTTPServer(("127.0.0.1",0),Handler) as srv:
        thread=Thread(target=srv.serve_forever,daemon=True);thread.start()
        base=f"http://127.0.0.1:{srv.server_port}"
        def get(path):
            with urlopen(base+path,timeout=10) as response:return response.read()
        def data(path):return json.loads(get(path))
        try:
            assert b'href="/compact"' in get("/") and b"Compact version history" in get("/compact")
            assert data("/api")["journal_title"]=="Robert Dinesen"
            v=data("/api/compact")
            assert v["case"]=="reinforce" and v["full"]["title"]=="Jay Craven" and len(v["full"]["rows"])==2 and len(v["compact"]["rows"])==1
            for case,c in serve.CASES.items():
                for receive in range(c["cuts"]+1):
                    for t in range(receive+1):
                        for flag in (0,1):
                            qs=f"?case={case}&received={receive}&asof={t}&mention={flag}"
                            z=data("/api/compact"+qs)
                            original=data("/api"+qs)
                            a,b=z["full"],z["compact"]
                            expected=max(c["candidates"],key=lambda x:(x["boosted"] if x["seen"] is not None and x["seen"]<=t and (flag or x["id"]!=c["target"]) else x["base"],-x["rank"],-x["id"]))
                            assert z["equal"] and a["id"]==b["id"]==expected["id"]==original["journal"]["winner"]
                            assert a["bits"]==b["bits"] and len(b["rows"])<=len(a["rows"])
                            assert len(b["rows"])==1+sum(r[1]!=s[1] for r,s in zip(a["rows"],a["rows"][1:]))
                            tested+=1
            for bad in ["/compact?received=-1","/api/compact?case=bad"]:
                try:get(bad);raise AssertionError("expected invalid controls")
                except HTTPError as exc:assert exc.code==400
        finally:srv.shutdown();thread.join()
    print(f"Passed original console and {tested} full-vs-compact historical HTTP comparisons.")
if __name__=="__main__":main()
