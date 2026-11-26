"""Start the actual loopback server at an ephemeral port and verify the archived q11 transition."""
import json,re,subprocess,sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen
HERE=Path(__file__).resolve().parent
def main():
    p=subprocess.Popen([sys.executable,str(HERE/"server.py"),"--port","0"],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        base=p.stdout.readline().strip()
        assert re.fullmatch(r"http://127\.0\.0\.1:\d+",base),base
        def fetch(route):
            with urlopen(base+route,timeout=8) as f:return f.read()
        def obj(route):return json.loads(fetch(route))
        assert obj("/api/health")=={"status":"ok","episode":"q11"}
        html=fetch("/").decode();assert '<html lang="en">' in html and "Evidence history" in html and "История свидетельств" in html
        state=obj("/api/state");assert state["horizon"]==17 and state["version"]==16
        assert state["previous_commit"]==state["query"]=={"interval":[14,2],"journal":[14,2]}
        assert state["current"]=={"interval":[3,1],"journal":[3,1]}
        assert state["changes_at_horizon"]==[{"from":14,"to":19,"delta":-1,"was":1,"now":0}]
        assert state["born_at_horizon"]==[21,22] and state["message_boundary"]==49
        trace=json.loads((HERE/"trace.json").read_bytes())["trace"]
        for h in range(len(trace)+1):
            report=obj("/api/state?horizon="+str(h)+"&version="+str(h))
            expect=trace[h-1]["winner"] if h else None
            assert report["query"]=={"interval":expect,"journal":expect} and report["current"]==report["query"]
        for route,status in [("/api/state?horizon=3&version=4",400),("/api/state?horizon=-1",400),
                             ("/api/state?horizon=33",400),("/api/state?version=bad",400),("/not-a-file",404)]:
            try:fetch(route);raise AssertionError(route)
            except HTTPError as e:assert e.code==status
        assert any("PRIMARY KEY" in s.upper() for s in state["plans"]["journal"])
        print("PASS 33 commit horizons, historical witness, 2 real SQLite plans, invalid-input HTTP codes")
    finally:
        p.terminate();out,err=p.communicate(timeout=8);assert not out and not err,(out,err)

if __name__=="__main__":main()

