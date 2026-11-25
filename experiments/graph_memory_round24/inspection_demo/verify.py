"""Independent source-level numerical audit using explicit character sets."""
from collections import defaultdict
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
from store import connect,cases,view,FORMATS,POLICIES
from build import D,W,R,P,REC,M,A,CACHE,TOK,read,sha,save,cid
sys.path.insert(0,str(R/"field_first"))
from decide import rank,visible,Tokenizer
def coords(spans):
    return {(e,x) for e,a,b in spans for x in range(a,b)}
def open_independently(tokenizer,field,a,body):
    text=f"[{field}:{a}] "+body[a:];header=len(text)-len(body[a:])
    tok=tokenizer.encode(text,add_special_tokens=False)
    right=tok.offsets[256][0] if len(tok.ids)>256 else len(text)
    while len(tokenizer.encode(text[:right],add_special_tokens=False).ids)>256:right-=1
    return [field,a,a+right-header,len(tokenizer.encode(text[:right],add_special_tokens=False).ids)]
def all_windows(parts,body,tok):
    result=[]
    for e,a,b in parts:
        val=body[e][a:b];ofs=tok.encode(val,add_special_tokens=False).offsets
        for i in range(0,max(len(ofs),1),128):
            lo=ofs[i][0] if i else 0;end=min(i+128,len(ofs));hi=ofs[end][0] if end<len(ofs) else len(val)
            result.append((e,a+lo,a+hi,end-i))
    return result
def main():
    tok=Tokenizer.from_file(str(TOK))
    off=W/"graph_memory_round18/isetrace_official"
    gold=read(off/"gold-spans.json.gz");old=read(M/"per-query.json.gz");rc=read(REC/"per-query.json.gz")["rows"]
    aorig=read(A/"per-query.json.gz")["rows"]
    reg=sqlite3.connect((P/"registry.sqlite").resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    checks=defaultdict(int)
    with closing(connect()) as db:
        ids={r["id"] for r in cases(db)}
        for i in range(8):
            receipts=read(P/f"receipts-{i}.json.gz")
            receiver=read(REC/f"receiver-{i}.json.gz")
            for r in receipts:
                q,t=r["q"],r["t"];key=cid(q)
                if key not in ids:continue
                raw=read(CACHE/f"{i}-{t}.json.gz");qq=dict(raw["q"])[q]
                book={};body={}
                for num,eid,pointer in reg.execute("SELECT e,eid,ptr FROM address WHERE t=?",(t,)):
                    book[eid,pointer]=num;body[num]=raw["fields"][eid]
                truth=coords([(book[s["event_id"],s["json_pointer"]],s["char_start"],s["char_end"]) for s in gold[q]])
                for fmt in FORMATS:
                    external=receiver[q];part="merged" if fmt=="sender" else "short"
                    archived=r["arms"]["ratio/"+part]["paid"]["2048"]
                    parts=external["shown"] if fmt=="receiver" else archived[2]
                    memory=coords(parts)
                    internal=external["tokens_internal"] if fmt=="receiver" else archived[0]
                    wins=visible(parts,body,tok);sorted_rows=rank(wins,qq)
                    sizes=all_windows(parts,body,tok)
                    assert len(wins)==len(sizes) and all(w[:2]==s[:2] for w,s in zip(wins,sizes))
                    def pred(j):
                        e,l,h,n=sizes[j]
                        pay=256-len(tok.encode(f"[{e}:{l}] ",add_special_tokens=False).ids)
                        right=min(len(body[e]),l+(pay*(h-l)//n if n else pay))
                        return sum((e,k) not in memory for k in range(l,right))
                    for policy in POLICIES:
                        snap=view(db,key,fmt,policy);m=snap["metrics"]
                        selected=(sorted_rows[0] if sorted_rows else None) if policy=="bm25" else next((j for j in sorted_rows if pred(j)>0),None)
                        op=None
                        if selected is not None:op=open_independently(tok,*sizes[selected][:2],body[sizes[selected][0]])
                        found=coords([op[:3]]) if op else set()
                        assert snap["source"]==([op[:3]] if op else []) and m["open_wp"]==(op[3] if op else 0)
                        assert (snap["estimated_new_chars"],snap["rank"])==((pred(selected),sorted_rows.index(selected)+1) if selected is not None else (None,None))
                        assert snap["memory"]==parts
                        assert m["wire_wp"]==archived[0] and m["wire_bytes"]==archived[1] and m["inside_wp"]==internal
                        exact={"gold":len(truth),"memory_gold":len(memory&truth),"new_gold":len((found-memory)&truth),
                             "missing":len(truth-(memory|found)),"returned":len(found),"added_source":len(found-memory),
                             "memory_chars":len(memory),"full":truth<=memory|found,"initial_full":truth<=memory}
                        assert all(m[k]==v for k,v in exact.items()),key
                        for k,expected in (("memory",truth&memory),("added",(found-memory)&truth),("missing",truth-(found|memory))):
                            assert coords([v[:3] for v in snap["components"] if v[3]==k])==expected
                        assert m["total_wp"]==m["wire_wp"]+m["open_wp"]<=2304
                        checks["condition_cells"]+=1
                        if fmt=="sender":
                            st=old[q]["arms"][policy]
                            assert (m["new_gold"],m["full"],m["added_source"],m["returned"],m["open_wp"],m["total_wp"])==(st["gold_gain_chars"],bool(st["union_fs"]),st["added_source_chars"],st["returned_source_chars"],st["open_tokens"],st["all_tokens"])
                            checks["sender_metrics_match_sealed_r23"]+=1
                        if policy=="bm25":
                            stored=(rc[q]["values"]["receiver_read"] if fmt=="receiver" else aorig[q]["outcomes"]["ratio/"+part+"/bm25"])
                            assert abs(len(truth&found)/len(truth)-stored[2])<1e-12
                            checks["bm25_open_coverage_matches_r23"]+=1
                        if snap["origin"]=="R24":checks["fresh_policies_independently_recomputed"]+=1
        try:
            db.execute("UPDATE sample SET reason='test' WHERE 0")
        except sqlite3.OperationalError:checks["reject_write"]=True
        else:raise RuntimeError("Write unexpectedly accepted.")
    reg.close()
    assert checks["condition_cells"]==len(ids)*6
    checks["cases"]=len(ids)
    save(D/"verification.json",dict(checks=checks,db=sha(D/"inspection.sqlite"),snapshot=sha(D/"inspection.html"),verifier=sha(Path(__file__))))
    print(dict(checks))
if __name__=="__main__":main()
