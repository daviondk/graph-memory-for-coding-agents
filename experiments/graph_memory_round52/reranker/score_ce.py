"""Pairwise cross-encoder inference, independent of annotations."""
from concurrent.futures import ThreadPoolExecutor
import math
from threading import local
from common import *

DIGEST="5290f5b9a2636be40baf807feafcfb222e0c4670a083fb3447d87993566190a9"
def main():
    old=read(R50.parent/"graph_memory_round46/reader_transfer/plan.json")
    assert sha(CE)==DIGEST and sha(EXE)==old["server"]
    inputs={};catalogs={}
    for panel,(src,scratch) in PANELS.items():
        f=scratch/"catalog-input.json.gz";expected=read(src/"projection-seal.json")["visible"]
        assert sha(f)==expected
        inputs[panel]=expected;catalogs[panel]=read(f)
    put("registration.json",dict(protocol=sha(D/"PROTOCOL_RU.md"),ckpt=DIGEST,exe=sha(EXE),inputs=inputs,
        instruction=INSTRUCTION,code=sha(Path(__file__)),expected_n=[640,1280,1280]))
    todo=[(panel,q,*catalogs[panel][q]) for panel in PANELS for q in sorted(catalogs[panel])]
    out={k:{} for k in PANELS}
    settings=["--rerank","--pooling","rank","-np","4","-c","8192","-b","4096","-ub","2048","-t","3","-tb","3","--offline","-lv","2"]
    with server(CE,settings,"ce",18934) as (url,_,hw):
        worker=local()
        def call(row):
            panel,q,question,snippet,titles=row
            if not hasattr(worker,"http"):worker.http=session()
            query="Instruct: "+INSTRUCTION+"\nQuery: "+question+"\n"+snippet
            start=time.perf_counter()
            res=worker.http.post(url+"/v1/rerank",json=dict(query=query,documents=[t for _,t in titles],top_n=len(titles),return_documents=False),timeout=240)
            res.raise_for_status();js=res.json();a=js["results"]
            assert sorted(v["index"] for v in a)==list(range(len(titles)))
            scores={str(titles[v["index"]][0]):float(v["relevance_score"]) for v in a}
            assert all(math.isfinite(v) for v in scores.values())
            return panel,q,dict(scores=scores,seconds=time.perf_counter()-start,usage=js.get("usage",{}))
        journal=RUN/"ce.jsonl"
        # Resume completed groups only when the entire protocol and inputs match.
        ticket=sha(D/"registration.json")
        journal=RUN/("ce-"+ticket+".jsonl")
        if journal.exists():
            for line in journal.read_bytes().splitlines():
                p,q,row=json.loads(line);out[p][q]=row
        remainder=[row for row in todo if row[1] not in out[row[0]]]
        start=time.perf_counter()
        with journal.open("a",encoding="utf8") as log, ThreadPoolExecutor(max_workers=4) as pool:
            for i,(p,q,value) in enumerate(pool.map(call,remainder)):
                log.write(json.dumps([p,q,value],separators=(",",":"))+"\n")
                out[p][q]=value
                if i%80==0:log.flush();print(i+1,"/",len(remainder),round(time.perf_counter()-start,1),flush=True)
        duration=time.perf_counter()-start
        replay={}
        for p in PANELS:
            cases=[r for r in todo if r[0]==p][:2]
            for row in cases:
                _,q,r=call(row);orig=out[p][q]["scores"]
                replay[q]=dict(first=orig,repeat=r["scores"])
        assert all(set(out[k])==set(catalogs[k]) for k in PANELS)
        put("ce-scores.json.gz",out);put("ce-replay.json",replay)
        put("ce-seal.json",dict(scores=sha(D/"ce-scores.json.gz"),registration=ticket,server=hw,seconds=duration,
            fresh=len(remainder),n=len(todo),pairs=sum(len(r["scores"]) for v in out.values() for r in v.values()),
            replay=sha(D/"ce-replay.json")))
        print("Sealed",get("ce-seal.json")["pairs"],"pair scores",flush=True)
if __name__=="__main__":main()

