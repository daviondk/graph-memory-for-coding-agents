"""Execute real HTTP requests and verify SQL winners for every bundled historical prefix."""
import json
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError
from urllib.request import urlopen
from serve import CASES,Handler

class Quiet(Handler):
    def log_message(self,*args):pass

def main():
    checked=0
    with ThreadingHTTPServer(("127.0.0.1",0),Quiet) as server:
        thread=Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f"http://127.0.0.1:{server.server_port}"
        def get(path):
            with urlopen(base+path,timeout=5) as res:return res.read()
        try:
            assert b"Versioned retrieval" in get("/")
            for key,case in CASES.items():
                for received in range(case["cuts"]+1):
                    for asof in range(received+1):
                        for flag in (0,1):
                            d=json.loads(get(f"/api?case={key}&received={received}&asof={asof}&mention={flag}"))
                            c=max(case["candidates"],key=lambda v:(v["boosted"] if v["seen"] is not None and
                                v["seen"]<=asof and (flag or v["id"]!=case["target"]) else v["base"],-v["rank"],-v["id"]))
                            assert d["journal"]["winner"]==d["eligible"]["winner"]==c["id"]
                            assert len(d["history"])<=d["journal"]["bound"]
                            assert bool(d["changed"])==(key=="change" and asof>=2)
                            checked+=1
            d=json.loads(get("/api?case=reinforce"))
            assert len(d["history"])==2 and d["history"][0]["title"]==d["history"][1]["title"]
            assert d["history"][0]["score"]<d["history"][1]["score"]
            assert json.loads(get("/api?case=change&received=1&asof=2"))["asof"]==1
            for url,expected in [("/api?case=absent",400),("/api?received=-1",400),("/api?mention=nah",400),("/nothing",404)]:
                try:get(url);raise AssertionError("missing error")
                except HTTPError as err:assert err.code==expected
        finally:server.shutdown();thread.join()
    print(f"Passed {checked} historical/counterfactual HTTP comparisons, three scenarios and 4 error cases.")
if __name__=="__main__":
    main()
