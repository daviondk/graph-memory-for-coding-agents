"""Independent interval, linkage, and statistical audit. Does not import any study code."""
from collections import Counter,defaultdict
from pathlib import Path
from statistics import mean
import gzip,hashlib,json,sqlite3,sys
import numpy as np

D=Path(__file__).resolve().parent;R23=D.parent;W=R23.parent
CAUSE=R23/"read_causes";OPEN=R23/"address_open";FIELD=R23/"field_first";RECEIVE=R23/"receiver_merge"
R22=W/"graph_memory_round22/packing_control";OFF=W/"graph_memory_round18/isetrace_official"
CACHE=Path("D:/CodexResearch/x20-isetrace-e5-gpu/cache/projection")
TOK=Path("D:/CodexResearch/x20-isetrace-runtime/inputs/tokenizer.json")
def load(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    b=json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()+b"\n"
    p.write_bytes(gzip.compress(b,mtime=0) if p.suffix==".gz" else b)
def validate(d,lock):
    x=load(d/lock)
    for name,h in x["files"].items():assert sha(d/name)==h
    return sha(d/lock)
def canonical(spans):
    by=defaultdict(list)
    for e,a,b in spans:
        if b>a:by[e].append((a,b))
    out=[]
    for e,rs in sorted(by.items()):
        for a,b in sorted(rs):
            if out and out[-1][0]==e and a<=out[-1][2]:out[-1][2]=max(b,out[-1][2])
            else:out.append([e,a,b])
    return out
def metrics(gs,visible):
    # Integrate the overlap of two indicator functions using endpoint events.
    cover=0;den=0;status=4
    by=defaultdict(list)
    for e,l,h in visible:
        if h>l:by[e].append((l,h))
    for e,l,h in gs:
        v=by[e]
        if not v:status=0
        elif all(y<=l or x>=h for x,y in v):status=min(status,1)
        elif not any(x<=l and y>=h for x,y in v):
            spans=canonical((e,x,y) for x,y in v)
            status=min(status,3 if any(x<=l and h<=y for _,x,y in spans) else 2)
    timeline=defaultdict(lambda:defaultdict(lambda:[0,0]))
    for role,parts in enumerate((gs,visible)):
        for e,a,b in parts:
            if b>a:timeline[e][a][role]+=1;timeline[e][b][role]-=1
    for events in timeline.values():
        active=[0,0];prev=0
        for pos,(da,db) in sorted(events.items()):
            length=pos-prev
            if active[0]:den+=length;cover+=length*bool(active[1])
            active[0]+=da;active[1]+=db;prev=pos
    assert den>0 and (cover==den)==(status>=3)
    return int(cover==den),int(status==4),cover/den,status

def open_metrics(gs,one):
    e,l,h,tok=one
    assert 0<=tok<=256
    vals=metrics(gs,[(e,l,h)] if h>l else [])
    return [vals[0],int(any(z[0]==e for z in gs)),vals[2],tok]

def boot(vectors):
    by=defaultdict(list)
    for t,vec in vectors:by[t].append(vec)
    s=np.array([np.sum(by[t],axis=0) for t in sorted(by)]);size=np.array([len(by[t]) for t in sorted(by)])
    rng=np.random.default_rng(23609);boots=[]
    for _ in range(200):
        ix=rng.integers(len(s),size=(50,len(s)))
        boots.append(s[ix].sum(axis=1)/size[ix].sum(axis=1)[:,None])
    ci=np.quantile(np.vstack(boots),[.025,.975],axis=0);return ci
def main():
    gold=load(OFF/"gold-spans.json.gz");cohort={r["query_id"]:r for r in load(OFF/"cohort.json")}
    assert set(gold)==set(cohort) and len(gold)==2000
    audit={str(p.relative_to(R23)):validate(p,n) for p,n in ((CAUSE,"receipt-lock.json"),(OPEN,"read-lock.json"),(FIELD,"read-lock.json"),(RECEIVE,"receiver-lock.json"))}
    goldsha=sha(OFF/"gold-spans.json.gz");registry=sqlite3.connect((CAUSE/"registry.sqlite").as_uri()+"?mode=ro&immutable=1",uri=True)
    cause_ref=load(CAUSE/"per-query.json.gz")["questions"];open_ref=load(OPEN/"per-query.json.gz")["rows"];field_ref=load(FIELD/"per-query.json.gz")["rows"]
    states={};summary=defaultdict(list);counts=Counter();changes=Counter()
    named=("short_plain","short_intact","sender_intact","receiver_intact","receiver_fs","sender_fs","bm_short","bm_sender","bm_receiver","anchor_first","anchor_lex","lex_first","augment_anchor_first","augment_anchor_lex","augment_bm_sender","augment_bm_short","augment_bm_receiver","sender_initial","receiver_initial")
    for i in range(8):
        cp=load(CAUSE/f"receipts-{i}.json.gz");op=load(OPEN/f"reads-{i}.json.gz");fp=load(FIELD/f"reads-{i}.json.gz");rp=load(RECEIVE/f"receiver-{i}.json.gz")
        ad={r["t"]:r["addresses"] for r in load(R22/f"no-next-decisions-{i}.json.gz")}
        for t,v in ad.items():
            assert v==[list(z) for z in registry.execute("select eid,ptr from address where t=? order by e",(t,))]
        for row in cp:
            t,q=row["t"],row["q"];assert q not in states and t==cohort[q]["trajectory_id"]==op[q]["t"]==fp[q]["t"]==rp[q]["t"]
            mapping={tuple(a):e for e,a in enumerate(ad[t])}
            gs=[(mapping[(z["event_id"],z["json_pointer"])],z["char_start"],z["char_end"]) for z in gold[q]]
            initial={};vals={};question_mode=cohort[q]["memory_mode"];stratum=question_mode+"/"+("one" if len({g[0] for g in gs})==1 else "many")
            for a,control in row["arms"].items():
                for budget,(paid,nbytes,pieces,checksum) in control["paid"].items():
                    x=metrics(gs,pieces);st=cause_ref[q]["values"][a+"/"+budget]
                    assert list(x[:3])+[paid,nbytes,len(pieces),x[3]]==st
                    counts["initial_format_budget"]+=1
                    if budget=="2048":initial[a]=(x,pieces)
            for a,z in op[q]["read"].items():
                test=open_metrics(gs,z);assert test==open_ref[q]["outcomes"][a]
                counts["open_window"]+=1
            for a,z in fp[q]["read"].items():
                test=open_metrics(gs,z);assert test==field_ref[q]["values"][a]
                counts["field_offset"]+=1
                fmt="/".join(a.split("/")[:2])
                if a.endswith("/anchor/first"):assert z==op[q]["read"][fmt+"/first"]
                elif a.endswith("/lex/lex"):assert z==op[q]["read"][fmt+"/bm25"]
            short,visible=initial["ratio/short"];merged,sent=initial["ratio/merged"];recv=rp[q]
            client=metrics(gs,recv["shown"]);raw_union=canonical(visible);out_union=canonical(recv["shown"])
            changes["receiver_cut"]+=int(raw_union!=out_union)
            changes["receiver_over_limit_render"]+=int(recv["raw"]>2048)
            assert all(any(e==f and l2<=l and h<=h2 for f,l2,h2 in raw_union) for e,l,h in out_union)
            assert recv["tokens_internal"]<=2048 and recv["tokens_in"]==row["arms"]["ratio/short"]["paid"]["2048"][0]
            z_bm=op[q]["read"]["ratio/merged/bm25"];z_bshort=op[q]["read"]["ratio/short/bm25"]
            z_a=fp[q]["read"]["ratio/merged/anchor/first"];z_l=fp[q]["read"]["ratio/merged/anchor/lex"]
            z_lexfirst=fp[q]["read"]["ratio/merged/lex/first"];z_r=recv["opened"]
            for z,ranges in ((z_bm,sent),(z_a,sent),(z_l,sent),(z_r,recv["shown"])):
                if z[0]>=0:assert any(v[0]==z[0] and v[1]<=z[1]<v[2] for v in ranges)
            vals=dict(zip(named,[short[0],short[1],merged[1],client[1],client[0],merged[0],open_metrics(gs,z_bshort)[0],open_metrics(gs,z_bm)[0],open_metrics(gs,z_r)[0],open_metrics(gs,z_a)[0],open_metrics(gs,z_l)[0],open_metrics(gs,z_lexfirst)[0],metrics(gs,sent+[z_a[:3]])[0],metrics(gs,sent+[z_l[:3]])[0],metrics(gs,sent+[z_bm[:3]])[0],metrics(gs,visible+[z_bshort[:3]])[0],metrics(gs,recv["shown"]+[z_r[:3]])[0],merged[0],client[0]],strict=True))
            states[q]={"t":t,"stratum":stratum,"v":vals}
            for k,z in vals.items():summary[k].append(z)
            assert client[0]<=short[0] and client[1]<=short[0]
            changes["receiver_token_repacked"]+=int(recv["tokens_internal"]!=recv["tokens_in"])
    registry.close()
    assert len(states)==2000 and len({z['t'] for z in states.values()})==1207
    pairs=[("sender_intact","short_intact"),("receiver_intact","short_intact"),("sender_intact","receiver_intact"),("sender_fs","receiver_fs"),("bm_sender","bm_receiver"),("bm_sender","bm_short"),("anchor_lex","bm_sender"),("anchor_lex","anchor_first"),("anchor_first","lex_first"),("augment_anchor_lex","augment_anchor_first"),("augment_anchor_lex","augment_bm_sender"),("augment_bm_sender","augment_bm_receiver"),("augment_bm_sender","augment_bm_short"),("augment_anchor_lex","sender_initial")]
    vs=[(z["t"],[z["v"][l]-z["v"][r] for l,r in pairs]) for q,z in sorted(states.items())]
    ci=boot(vs)
    dif={l+"-"+r:{"left":sum(summary[l]),"right":sum(summary[r]),"delta":(sum(summary[l])-sum(summary[r]))/2000,"gains":sum(v[k]>0 for _,v in vs),"losses":sum(v[k]<0 for _,v in vs),"paired_cluster95":ci[:,k].tolist()} for k,(l,r) in enumerate(pairs)}
    samples={};strata={}
    for name in sorted({z["stratum"] for z in states.values()}):
        subset={q:z for q,z in states.items() if z["stratum"]==name}
        ordered=sorted(subset,key=lambda q:hashlib.sha256(("r23-audit/"+q).encode()).digest())
        samples[name]=ordered[:16];strata[name]={"n":len(subset),"trajectories":len({z["t"] for z in subset.values()}),"hits":{k:sum(z["v"][k] for z in subset.values()) for k in named}}
    save(D/"sample.json",samples);save(D/"recomputed.json.gz",states)
    save(D/"numerical.json",{"locks":audit,"counts":counts,"receiver":changes,"gold":goldsha,"n":len(states),"strata":strata,"hits":{k:sum(v) for k,v in summary.items()},"comparisons":dif,"per_query":sha(D/"recomputed.json.gz"),"selection":sha(D/"sample.json"),"code":sha(Path(__file__))})
if __name__=="__main__":main()

