"""Independent matched-cost, source-mask, frontier-routing and attainability sanity check."""
from collections import Counter,defaultdict
from functools import lru_cache
import hashlib,json,gzip,math,re,runpy,sqlite3,sys
from pathlib import Path
D=Path(__file__).resolve().parent
W=D.parents[1];P=W/"graph_memory_round23";F=D.parent/"frontier_open";C=D.parent/"attainable_open"
sys.path.insert(0,str(P/"transfer"));import common as md
from tokenizers import Tokenizer
def read(path):return json.loads(gzip.decompress(path.read_bytes()) if path.suffix==".gz" else path.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def sortkey(k):return hashlib.sha256(("r24-release-check-v1:"+k).encode()).digest()
def points(s):return {(e,i) for e,a,b in s for i in range(a,b)}
def amount(tok,s):return len(tok.encode(s,add_special_tokens=False).ids)
def opened(tok,bodies,e,start,cap=256,stop=None):
    head=f"[{e}:{start}] ";body=bodies[e][start:stop]
    text=head+body
    enc=tok.encode(text,add_special_tokens=False)
    right=enc.offsets[cap][0] if len(enc.ids)>cap else len(text)
    while amount(tok,text[:right])>cap:right-=1
    return [e,start,start+max(0,right-len(head)),amount(tok,text[:right])]
def windows(parts,bodies,tok):
    result=[]
    for e,a,b in parts:
        s=bodies[e][a:b];o=tok.encode(s,add_special_tokens=False).offsets
        for i in range(0,max(1,len(o)),128):
            l=o[i][0] if i else 0;end=o[i+128][0] if i+128<len(o) else len(s)
            result.append([e,a+l,s[l:end]])
    return result
def ranking(win,q):
    parse=lambda s:Counter(re.findall(r"[^\W_]+",s.casefold(),re.UNICODE))
    terms=set(parse(q));documents=[parse(s) for e,a,s in win]
    lengths=[sum(d.values()) for d in documents];n=len(win);mean=sum(lengths)/max(n,1) or 1
    idf={w:math.log1p((n-df+.5)/(df+.5)) for w in terms if (df:=sum(w in d for d in documents))}
    val=[sum(idf[w]*2.2*counter[w]/(counter[w]+1.2*(.25+.75*L/mean)) for w in sorted(terms&counter.keys())) for counter,L in zip(documents,lengths)]
    return sorted(range(n),key=lambda j:(-val[j],j))
def audit():
    a=read(C/"per-query.json.gz");sum_a=read(C/"results.json")
    g=read(F/"per-query.json.gz")["corpora"];sum_g=read(F/"results.json")
    assert sha(C/"per-query.json.gz")==sum_a["per_query"] and sha(F/"per-query.json.gz")==sum_g["outcomes"]
    assert sha(F/"action-lock.json")==sum_g["seal"]
    domains=md.get_views();docs={j:r[2] for j,r in enumerate(domains["documents"])};md_q={r[0]:r[2] for r in domains["q"]}
    truth_md,_=runpy.run_path(str(P/"transfer/score.py"),run_name="independent_gold")["labels"](domains)
    truth_i=read(W/"graph_memory_round18/isetrace_official/gold-spans.json.gz")
    ise_root=P/"read_causes";reg=sqlite3.connect((ise_root/"registry.sqlite").resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    raw_c=Path("D:/CodexResearch/x20-isetrace-e5-gpu/cache/projection")
    per={}
    for tag in ("isetrace","multidoc"):
        rr=a[tag];rows=g[tag];file=F/f"actions-{tag}.json.gz";acts=read(file)
        assert sha(file)==read(F/"action-lock.json")["files"][file.name]
        scores=sum_g["results"][tag]["summary"];summ=sum_a["summary"][tag]
        assert set(rr)==set(rows)==set(acts) and len(acts)==summ["n"]
        count=Counter();n=len(rr)
        for q,x in rr.items():
            count["base"]+=x["base"];assert x["base"]==rows[q]["base"]
            if not x["base"]:
                count["incomplete"]+=1;count["one_field_possible"]+=x["missing_fields"]==1
                count["multi_field"]+=x["missing_fields"]>1;count["one_visible_field_possible"]+=x.get("field_visible",0)
                count["gold_start_any"]+=x.get("gold_start_fits",0);count["gold_start_visible"]+=x.get("gold_start_fits",0)*x.get("field_visible",0)
                count["legal_window"]+=bool(x.get("legal_successes",0))
        assert all(count[k]==summ.get(k,0) for k in count)
        for name,s in scores.items():
            v=[r["scores"][name] for r in rows.values()]
            for i,k in enumerate(("hits","coverage","added_chars","tokens","abstain","empty_reads")):
                vtotal=sum(z[i] for z in v)
                assert abs((vtotal/n if i in (1,2,3) else vtotal)-s[k])<1e-9
        assert all(r["scores"]["right_edge_matched"][3]==r["scores"]["first_positive_matched"][3] for r in rows.values())
        first=sorted(rr,key=sortkey)[:10]
        incomplete=sorted((q for q in rr if not rr[q]["base"] and rr[q].get("field_visible")),key=sortkey)[:5]
        chosen=list(dict.fromkeys(first+incomplete))
        tok=md.tok() if tag=="multidoc" else Tokenizer.from_file("D:/CodexResearch/x20-isetrace-runtime/inputs/tokenizer.json")
        if tag=="isetrace":
            shard_by_t={}
            for i in range(8):
                for row in read(ise_root/f"receipts-{i}.json.gz"):
                    if row["q"] in chosen:shard_by_t[row["t"]]=i
        tested_open=0;legal_checked=0
        for q in chosen:
            if tag=="multidoc":
                native_spans=truth_md[q][0];qs=md_q[q];bod=docs
            else:
                t=acts[q]["t"];data=read(raw_c/f"{shard_by_t[t]}-{t}.json.gz")
                qr={(eid,p):e for e,eid,p in reg.execute("SELECT e,eid,ptr FROM address WHERE t=?",(t,))}
                native_spans=[(qr[s["event_id"],s["json_pointer"]],s["char_start"],s["char_end"]) for s in truth_i[q]]
                qs=dict(data["q"])[q];bod={e:data["fields"][eid] for (eid,_),e in qr.items()}
            truth=points(native_spans);actual=acts[q]["actions"];base=acts[q]["base"];shown=points(base);missing=truth-shown
            wins=windows(base,bod,tok);order=ranking(wins,qs);verified={}
            def walk(order):
                for j in order:
                    e,start,_=wins[j];end=start
                    while (e,end) in shown:end+=1
                    if end<len(bod[e]):return (e,start),(e,end)
                return None,None
            left,right=walk(order);_,unranked=walk(range(len(wins)))
            for k,coord in (("same_window",left),("right_edge",right),("first_edge",unranked)):
                assert (opened(tok,bod,*coord) if coord else None)==actual[k]
            for k,op in actual.items():
                if op:
                    e,l,h,nwp=op
                    assert 0<=l<=h<=len(bod[e]) and amount(tok,f"[{e}:{l}] "+bod[e][l:h])==nwp<=256
                    if not k.endswith("_matched"):assert opened(tok,bod,e,l)==op
                    tested_open+=1
                selected=points([op[:3]]) if op else set();un=truth&(shown|selected)
                ref=[int(un==truth),len(un)/len(truth),len(selected-shown),op[3] if op else 0,int(op is None),int(op is not None and not(selected-shown))]
                assert all(abs(x-y)<1e-12 for x,y in zip(ref,rows[q]["scores"][k]))
            assert int(not missing)==rr[q]["base"]
            if missing:
                assert len(missing)==rr[q]["missing_chars"] and len({k for k,x in missing})==rr[q]["missing_fields"]
                possible=0
                for e,start in sorted({(e,start) for e,start,_ in wins}):
                    if all(field==e and x>=start for field,x in missing):
                        op=opened(tok,bod,e,start)
                        possible+=all(x<op[2] for _,x in missing)
                    legal_checked+=1
                assert possible==rr[q].get("legal_successes",0)
                if rr[q]["missing_fields"]==1:
                    e=min(missing)[0];x=min(i for _,i in missing)
                    check=opened(tok,bod,e,x)
                    assert int(max(i for _,i in missing)<check[2])==rr[q]["gold_start_fits"]
        per[tag]=dict(all_rows=n,strictly_matched_all=n,hash_sample=len(first),additional_incomplete=len(chosen)-len(first),
                      validated_queries=chosen,validated_paid_reads=tested_open,legal_window_candidates_accounted=legal_checked,
                      counts=dict(count),hits_by_method={k:v["hits"] for k,v in scores.items()})
    reg.close()
    result=dict(status="pass",corpora=per,script=sha(Path(__file__)),attainable=sha(C/"results.json"),frontier=sha(F/"results.json"))
    (D/"results.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf8")
    print([(k,v["all_rows"],v["hash_sample"],v["additional_incomplete"],v["validated_paid_reads"],v["legal_window_candidates_accounted"]) for k,v in per.items()])
if __name__=="__main__":audit()
