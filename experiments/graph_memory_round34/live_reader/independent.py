"""Rebuild current graphs and actually invoke the native dense retriever on their visible candidates."""
from live import *
import hashlib,sqlite3
from functools import lru_cache
from graph_memory.retrieval.methods.flat.dense import DenseTaskRetriever
from graph_memory.retrieval.requests import TextRankingRequest
class Vectors:
    def __init__(self,db):
        self.db=db;self.unique=set();self.cache={}
    def encode(self,texts,**opts):
        assert opts==dict(batch_size=64,normalize_embeddings=True,show_progress_bar=False)
        keys=[hashlib.sha256(s.encode()).digest() for s in texts];self.unique.update(keys)
        lookup=self.cache;missing=[k for k in set(keys) if k not in lookup]
        for start in range(0,len(missing),200):
            sub=missing[start:start+200];p=",".join("?" for _ in sub)
            for k,v in self.db.execute("select k,v from vectors where prec='fp32' and k in ("+p+")",sub):lookup[k]=np.frombuffer(v,dtype="<f4")
        assert set(keys)<=set(lookup)
        return np.stack([lookup[k] for k in keys])
def main():
    allow={r["t"] for r in read(R22/"outcomes.json.gz") if not r["pilot"]}
    targets=sorted(allow,key=lambda s:hashlib.sha256(("r34-live-independent/"+s).encode()).digest())[:24]
    save(HERE/"audit-plan.json",{"targets":targets,"program":sha(Path(__file__)),"seal":sha(HERE/"seal.json")})
    db=sqlite3.connect(Path("D:/CodexResearch/x20-isetrace-trained/trained-vectors.sqlite3").as_uri()+"?mode=ro",uri=True)
    assert db.execute("select checkpoint from identity").fetchone()[0]==read(ref.TR/"prediction-plan.json")["weights_sha256"]
    vec=Vectors(db);dense=DenseTaskRetriever(model_name="D:/CodexResearch/x20-isetrace-trained/model",encoder=vec,device="cpu")
    tok=env.pilot.offsets(env.pilot.Tokenizer.from_file(str(env.pilot.CACHE/"tokenizer.json")))
    graph,rank,meta,patch,mp=read_models();cases={};states=0
    for sh in range(8):
        raw=env.RAW/f"trajectories-{sh:05d}.jsonl";canon={r["q"]:r for r in read(ref.TR/f"forecasts-main-{sh}.json.gz") if r["t"] in targets}
        recs={(r["q"],r["cut"]):r for r in read(HERE/f"forecast-{sh}.json.gz") if r["t"] in targets}
        for _,obj in env.pilot.stream(raw):
            t=obj["session_id"]
            if t not in targets:continue
            tr=parent.adapt_isetrace_record(parent.parse_isetrace_record(obj),source_revision=env.pilot.RAW[1])
            projection=read(Path("D:/CodexResearch/x20-isetrace-e5-gpu/cache/projection")/f"{sh}-{t}.json.gz")
            @lru_cache(maxsize=None)
            def chunks(s):return env.pilot.token_chunks(s,tokenizer=tok,max_tokens=504,overlap_tokens=64)
            for pct,step in zip((25,50,75,100),parent.cuts_for(tr.events)):
                prefix_tr=tr.model_copy(update={"events":tr.events[:step+1],"source_metadata":None,"final_response":"","source_total_steps":step+1})
                g=parent.build_provenance_graph(prefix_tr,content_chunker=chunks);ids,geom=geometry({"g":g.model_dump()})
                candidates=tuple(env.pilot.native.provenance_unit_candidates(g));states+=1
                ident=list(ids);mapping={c.item_id:{"source_spans":[s.model_dump() for s in c.source_spans],"token_count":c.metadata["token_count"] if isinstance(c.metadata,dict) else c.metadata.attrs["token_count"]} for c in candidates}
                assert set(mapping)==set(ident)
                assert [c.item_id for c in candidates]==[z["item_id"] for z in projection["pool"] if z["item_id"] in ids]
                facs,prices=features(ident,geom,mapping);sp=score(graph,facs)
                for q,question in projection["q"]:
                    if q not in canon:continue
                    ranked=dense.rank(TextRankingRequest(task_id=q,query_text=question,candidates=candidates));ordered=[z.node_id for z in ranked]
                    full=canon[q]["rr"];want=[v["node_id"] for v in full if v["node_id"] in ids]
                    lookup0={v["node_id"]:v["score"] for v in full}
                    dx=max(abs(z.score-lookup0[z.node_id]) for z in ranked);assert dx<1e-10
                    equal=ordered==want
                    ords=np.array([ids[x] for x in ordered]);n=len(ords);r=np.arange(1,n+1);c=prices[ords];role=facs[ords,0]
                    s=score(rank,np.column_stack([-np.log(r),1/r,(n-r)/max(1,n-1)]))+sp[ords]+correct(patch,np.column_stack([np.log1p(r),np.log1p(c),role,role*np.log1p(c)]))
                    compute=np.argsort(-s,kind="stable")
                    compare=[]
                    for b,stored in zip(BUDGETS,recs[q,pct]["selected"]["exact"]):
                        compare.append([ordered[j] for j in prefix(compute,c,b)]==[full[j]["node_id"] for j in stored])
                    cases[str(pct)+"/"+q]=[n,equal,dx,compare]
    db.close();assert len(targets)==24 and states==96 and len(cases)>=96
    save(HERE/"independent.json",{"histories":24,"states":states,"query_states":len(cases),"exact_selections":sum(sum(x[3]) for x in cases.values()),"total_selections":3*len(cases),"identical_dense":sum(x[1] for x in cases.values()),"max_score_diff":max(x[2] for x in cases.values()),"encoded_input_keys":len(vec.unique),"candidate_checks":sum(x[0] for x in cases.values()),"counts":cases,"plan":sha(HERE/"audit-plan.json")})
if __name__=="__main__":main()
