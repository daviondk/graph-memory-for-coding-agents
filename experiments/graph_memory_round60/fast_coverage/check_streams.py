"""Untimed full-trace equality check, including every LRU key, value and order after each query."""
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from resident_hit import ResidentHit,core
from residual import BlockStore,Residual,load,prepare,save
HERE=Path(__file__).resolve().parent
def main():
    import sys
    summaries={}
    original=load(HERE/"runs.json.gz")["blocks"][0]
    with TemporaryDirectory(dir=HERE) as tmp:
        path=Path(tmp)/"source.sqlite"
        for g,file in core.GROUPS.items():
            aggregate=Counter()
            for repo,events in load(file).items():
                ops,_=prepare(events,"B")
                db=BlockStore(path,"filelist",True);arms={}
                cut=sum(x[0]=="w" for x in ops)//2;idx=0
                logs=original[g+"/"+repo]["queries"]
                for op in ops:
                    if not arms and db.next_id==cut:
                        db.close();db=BlockStore(path,"filelist")
                        for cap in (1024,4096):
                            arms[cap]=[Residual(db,cap,"residual_only"),ResidentHit(db,cap,False),ResidentHit(db,cap,True)]
                    if op[0]=="w":
                        _,j,rev,ids=op;assert db.append(j,rev,ids)
                        for group in arms.values():
                            for h in group:h.committed(j,ids)
                    elif arms:
                        _,f,tie,prior,expected=op
                        assert logs[idx][:2]==[db.next_id,f]
                        for cap,group in arms.items():
                            for k,h in enumerate(group):
                                ans,s=h.read(f,tie,prior)
                                assert ans==expected
                                assert [s[a] for a in ("posting_bytes","body_bytes","posting_calls","body_calls")]==logs[idx][2][f"{cap}/residual_only"]
                                aggregate[f"{cap}/{k}/direct"]+=s["direct_resident"]
                                aggregate[f"{cap}/{k}/queries"]+=1
                            assert list(group[0].cache.items.items())==list(group[1].cache.items.items())==list(group[2].cache.items.items())
                            assert group[0].known==group[1].known==group[2].known
                            aggregate["per_query_state_checks"]+=2
                        idx+=1
                assert idx==len(logs)
                db.close();path.unlink()
            summaries[g]=aggregate
    dest=HERE/"stream-audit.json"
    if "--verify" in sys.argv:assert load(dest)==summaries
    else:save(dest,summaries)
    print(summaries)
if __name__=="__main__":main()

