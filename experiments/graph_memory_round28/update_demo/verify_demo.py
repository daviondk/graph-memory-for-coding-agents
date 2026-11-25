"""Check numeric decisions and serve the same controls over actual loopback HTTP."""
import json
import sqlite3
import threading
from urllib.error import HTTPError
from urllib.request import urlopen
from serve_demo import Inspector,ROOT,server

def verify():
    inspector=Inspector()
    with sqlite3.connect((ROOT/"sky.sqlite").as_uri()+"?mode=ro",uri=True) as db:
        assert db.execute("pragma integrity_check").fetchone()==("ok",)
    records=0
    for q,c in inspector.cases.items():
        for name,cut in c["projections"].items():
            r=inspector.inspect(q,*cut["cut"]);reference=inspector.answer(c["article"],cut["answer"])
            assert r["fixed"]==reference and r["base"]==inspector.answer(c["article"],c["answers"]["base"])
            if r["physically_measured"]:assert r["physical"]==inspector.answer(c["article"],c["answers"]["retract"])
            records+=1
        assert inspector.inspect(q,0,2**31-1)["fixed"] is None
    with server(0) as http:
        t=threading.Thread(target=http.serve_forever,daemon=True);t.start()
        try:
            home="http://127.0.0.1:"+str(http.server_port)
            def get(s):return urlopen(home+s,timeout=3).read()
            assert b'lang="ru"' in get("/")
            cases=json.loads(get("/api/cases"));assert len(cases)==96
            q=next(r["q"] for r in cases if r["diff"])
            r=json.loads(get("/api/read?q="+q));assert r["fixed"]["range"]!=r["physical"]["range"]
            for path in ("/api/read?q=invalid","/api/read?q="+q+"&start=-1&end=2","/api/read?q="+q+"&end=2"):
                try:get(path)
                except HTTPError as error:assert error.code==400
                else:raise AssertionError(path)
        finally:http.shutdown();t.join()
    return {"decisions":records,"empty_intervals":len(inspector.order),"http_cases":len(cases)}
if __name__=="__main__":print(json.dumps(verify()))
