"""Verify file integrity and exercise the actual HTTP readers and independent audits."""
from contextlib import ExitStack
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from demo import D, application, verify_assets
from threading import Thread

class Menu(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attributes):
        if tag == "a":
            self.links.append(dict(attributes)["href"])


def fetch(url, route, **query):
    with urlopen(url + route + "?" + urlencode(query), timeout=15) as response:
        return json.load(response)

def main():
    receipt = json.loads((D/"CONTENT_SHA256.json").read_bytes())
    for name, expected in receipt.items():
        if sha256((D/name).read_bytes()).hexdigest() != expected:
            raise ValueError("Digest mismatch: " + name)
    verify_assets()
    with ExitStack() as servers:
        landing = servers.enter_context(application(0))
        thread = Thread(target=landing.serve_forever, daemon=True)
        thread.start()
        servers.callback(thread.join, 4)
        servers.callback(landing.shutdown)
        start_url = f"http://127.0.0.1:{landing.server_port}"
        with urlopen(start_url + "/sessions.json", timeout=15) as res:
            sessions = json.load(res)
        assert set(sessions) == {"trace","code","context","flow","stream","core","address","policies","history","directory","churn"}
        with urlopen(start_url, timeout=15) as res:
            homepage = res.read().decode()
        assert "{{" not in homepage and all(url in homepage for url in sessions.values())
        menu = Menu()
        menu.feed(homepage)
        assert len(menu.links) == 15
        for url in menu.links:
            assert url.startswith("http://127.0.0.1:")
            with urlopen(url, timeout=15) as target:
                assert target.status == 200 and "text/html" in target.headers["Content-Type"]
        trace, code, context, flow, stream, learned, address = (
            sessions[k] for k in ("trace", "code", "context", "flow", "stream", "core", "address")
        )
        with urlopen(address, timeout=15) as res:
            assert "text/html" in res.headers["Content-Type"] and len(res.read()) > 500
        churn=sessions["churn"]
        assert fetch(churn,"/api/health")=={"status":"ok","episode":"q11"}
        c=fetch(churn,"/api/state",horizon=17,version=16)
        assert c["query"]=={"interval":[14,2],"journal":[14,2]}
        assert c["current"]=={"interval":[3,1],"journal":[3,1]}
        assert c["changes_at_horizon"]==[{"from":14,"to":19,"delta":-1,"was":1,"now":0}]
        assert fetch(churn,"/api/state",horizon=17,version=17)["query"]==c["current"]
        directory=sessions["directory"]
        cases=fetch(directory,"/api/cases")
        assert len(cases["examples"])==8 and cases["directory_size"]==5989847
        selection=fetch(directory,"/api/select",q=cases["default_q"],gate="59",mode="href")
        assert selection["selected"]["title"]=="Gabriel-Elzéar Taschereau"
        assert "support" not in selection and "expected_id" not in selection
        history=sessions["history"]
        compact=fetch(history,"/api/compact",case="reinforce")
        assert compact["equal"] and len(compact["full"]["rows"])==2 and len(compact["compact"]["rows"])==1
        for version,flag,title in ((1,1,"Dance Girl Dance"),(2,1,"Robert Dinesen"),(2,0,"Dance Girl Dance")):
            outcome=fetch(history,"/api",case="change",received=2,asof=version,mention=flag)
            assert outcome["journal_title"]==outcome["eligible_title"]==title
            assert len(outcome["history"])<=outcome["journal"]["bound"]
        replay_url=sessions["policies"]
        for panel,n,calls in [("gate_confirmation",1280,110),("adaptive_address",640,64),("transfer",640,90)]:
            diff=fetch(replay_url,"/api/compare",panel=panel,start="dense",end="registered")
            assert diff["n"]==n and diff["cold_delta"]["calls"]==calls
            assert diff["zero_omitted"]+len(diff["examples"])==n
            reversed_diff=fetch(replay_url,"/api/compare",panel=panel,start="registered",end="dense")
            assert diff["delta_f1_pp"]==-reversed_diff["delta_f1_pp"]
            same=fetch(replay_url,"/api/compare",panel=panel,start="0",end="0")
            assert not same["examples"] and same["cold_delta"]["calls"]==0
        assert diff["wins"]==16 and diff["losses"]==3
        categories=fetch(replay_url,"/api/rank/cases",panel="hotpot",category="gain")
        assert len(categories["summary"])==5 and categories["cases"]
        q=categories["cases"][0]["q"]
        a=fetch(replay_url,"/api/rank/query",panel="hotpot",q=q,method="graph")
        b=fetch(replay_url,"/api/rank/query",panel="hotpot",q=q,method="hybrid")
        assert a["recorded"]["f1"]>b["recorded"]["f1"] and a["winner"]!=b["winner"]
        for case in categories["cases"]:
            original=fetch(replay_url,"/api/rank/query",panel="hotpot",q=case["q"],method="graph")
            top=original["ordered"][0]
            if top["edge"]:
                disabled=fetch(replay_url,"/api/rank/query",panel="hotpot",q=case["q"],method="graph",suppress=top["cid"])
                if disabled["winner"]!=top["cid"]:
                    assert disabled["removed"]==top["cid"] and disabled["context"]==original["context"]
                    assert disabled["certificate"]==dict(agrees=True,original=top["cid"],predicted=disabled["winner"])
                    break
        else:
            raise AssertionError("Missing gain case with a decisive mention")
        panel_result=fetch(replay_url,"/api/rank/cases",panel="confirm",category="gain")
        scored={r["arm"]:r for r in panel_result["summary"]}
        assert 57.62<scored["graph"]["f1"]<57.63 and 55.71<scored["hybrid"]["f1"]<55.72
        health = fetch(address, "/api/health")
        assert health["ok"] and health["count"] == 1280
        assert abs(health["threshold"]-0.04178261756896973) < 1e-15
        for category, expected in (("all",1280),("switched",55),("gain",21),("loss",4)):
            cases = fetch(address, "/api/cases", filter=category, limit=2)
            assert cases["total"] == expected
            if category not in ("gain","loss"):
                continue
            key = cases["items"][0]["id"]
            chosen = fetch(address, "/api/case", id=key, threshold="registered")
            dense = fetch(address, "/api/case", id=key, threshold="0")
            assert chosen["changed"] and chosen["selected"] == chosen["mentioned"]
            assert 0 < chosen["gap"] <= health["threshold"]
            assert dense["selected"] == chosen["dense"] and not dense["changed"]
            active, base = chosen["selected_answer"], chosen["baseline_answer"]
            assert active["input_tokens"] == base["input_tokens"]
            assert active["prompt_sha"] != base["prompt_sha"] and active["snapshot"] == base["snapshot"]
            assert (active["f1"] > base["f1"]) == (category == "gain")
            assert "aliases" not in chosen and "supports" not in chosen
            annotation = fetch(address, "/api/gold", id=key)
            assert annotation["aliases"] and annotation["supports"]
            wrong = fetch(address, "/api/case", id=key, threshold="registered", snapshot="invalid")
            assert wrong["selected_answer"] is None
        for case in ("short","medium","long"):
            for step in (25,50,75,100):
                for policy in ("previous","greedy"):
                    trial=fetch(learned,"/core/audit",case=case,step=step,policy=policy)
                    assert trial["audit"]["equal"]
                    if (case,step,policy)==("long",100,"previous"):
                        assert (trial["work_cells"],trial["audit"]["full_cells"])==(22812,189290)
        from urllib.request import Request
        def visit(**data):
            req=Request(stream+"/api",data=json.dumps(data).encode(),headers={"Content-Type":"application/json"})
            with urlopen(req,timeout=15) as response:return json.load(response)
        for history in ("Short","Medium","Long"):
            for spacing in (0,4,16,64):
                packet=visit(action="open",trace=history,spacing=spacing)
                key=packet["session"]
                while True:
                    assert visit(action="audit",session=key)["verified"]
                    if packet["step"]==packet["total"]:break
                    packet=visit(action="advance",session=key,distance=1)
        projected=fetch(trace,"/api/weights/catalog")["queries"]
        assert len(projected)==40
        source=fetch(trace,"/api/weights/sources",q="q01")["sources"][0]["id"]
        for delta,n,tokens in ((6307132,9,2030),(6307133,13,2048)):
            answer=fetch(trace,"/api/weights/verify",q="q01",s=source,delta=delta)
            assert answer["verification"]["equal"] and len(answer["after"]["members"])==n and answer["after"]["tokens"]==tokens
        catalog=fetch(trace,"/api/joint/catalog")
        assert len(catalog["pairs"])==1862
        spec=catalog["example"]
        joint=fetch(trace,"/api/joint/audit",**spec)
        assert joint["audit"]["equal"]
        assert [joint["packets"][k]["id"] for k in ("base","first","second","joint")]==[352,352,352,355]
        for pair in (1,95,100):
            for x,y in ((0,0),(2**30,-2**30),(-2**30,2**30)):
                assert fetch(trace,"/api/joint/audit",pair=pair,x=x,y=y)["audit"]["equal"]
        cases=fetch(trace,"/api/observed/catalog")
        assert len(cases["groups"])==54
        for cap,subset,n in [(1,"all",19),(4,"5",19),(4,"18",19),(4,"5,18",15),(4,"all",15)]:
            case=fetch(trace,"/api/observed/check",q="q25",step=9,cap=cap,set=subset)
            assert case["checked"] and len(case["after"])==n and len(case["base"])==19
            if cap==4: assert all(x["preserves"] for x in case["updates"])
        visited=0
        for case in ("withdrawn","overlap","accumulating"):
            default=fetch(flow,"/snapshot",case=case)
            for step in range(1,1+default["total"]):
                audit=fetch(flow,"/audit",case=case,step=step)
                assert audit["audit"]["matches"] and audit["step"]==step
                visited+=1
        assert visited==84
        for policy, ids in [("file",[]),("range",[]),("edges",[0]),("local",[0,1])]:
            evidence=fetch(context,"/audit",case="interior",policy=policy,budget=2048)
            assert evidence["selected"]==ids and evidence["audit"]["mismatches"]==0
        initial = fetch(trace, "/api/packet", q="q02", b=2048)
        controls = [r for r in initial["sources"] if r["selected"]]
        for source in controls:
            new = fetch(trace, "/api/packet", q="q02", b=2048, s=source["id"])
            if new["added"] == [19] and new["removed"] == [11]:
                checked = fetch(trace, "/api/audit", q="q02", b=2048, s=source["id"])["audit"]
                assert checked["full_matches"] and checked["covered_chars"] == checked["gold_chars"] == 60
                break
        else:
            raise AssertionError("The documented selected-source example is missing")
        irrelevant = next(r["id"] for r in initial["sources"] if not r["selected"] and not r["barrier"])
        assert fetch(trace,"/api/packet",q="q02",b=2048,s=irrelevant)["action"] == "Reuse cached packet"
        for case, before, after in [("relocated",315,315),("changed",507,74),("stale",2044,2044)]:
            row = fetch(code, "/api/packet", case=case)
            assert (row["baseline"]["bytes"],row["span"]["bytes"]) == (before, after)
            audit = fetch(code, "/api/audit", case=case)
            if case=="relocated":
                assert audit["verified_reuse"]
            if case=="stale":
                assert len(audit["selected_mismatch"]) == 3
                assert audit["selected_mismatch"] == audit["selected_prior_mismatch"]
    print(f"Verified {len(receipt)} files and all eleven live SQLite consoles.")

if __name__=="__main__":
    main()
