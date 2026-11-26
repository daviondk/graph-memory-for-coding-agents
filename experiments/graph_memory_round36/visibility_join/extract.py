"""Build the call-level input from half-open witness intervals and an independent streaming PU oracle."""
from common import *
from collections import defaultdict
import sys,importlib.util,re
spec=importlib.util.spec_from_file_location("visibility_intervals",V/"study.py"); oracle=importlib.util.module_from_spec(spec);spec.loader.exec_module(oracle)
l=oracle.l;np=l.np
def setup():
    split=load(l.ref.TR/"split.json.gz")["test"]; h=sorted({r["t"] for r in split},key=key);assert len(h)==1207
    picks=h[:128];native=load(M/"plan.json")["audit_ids"]; allids=picks+sorted(set(native)-set(picks));return picks,native,allids
def run():
    primary,native,tids=setup(); ix={t:i for i,t in enumerate(tids)};targets=set(tids);rawplan=load(l.HERE/"plan.json");seal=load(M/"forecast-seal.json")["files"]
    plan={"panel_ids":[key(t) for t in primary],"native_ids":[key(t) for t in native],"native_hids":[ix[t] for t in native],"protocol":sha(D/"PROTOCOL_RU.md"),"oracle":sha(V/"study.py"),"r36":sha(M/"forecast-seal.json"),"native":sha(M/"native-raw-states.json.gz"),"extract":sha(D/"extract.py"),"common":sha(D/"common.py"),"raw_sha":rawplan["raw"]}
    if (D/"plan.json").exists():assert plan==load(D/"plan.json")
    else:save(D/"plan.json",plan)
    idx=l.ref.graph_index(); expected_native=load(M/"native-raw-states.json.gz");survival=load(V/"histories.json.gz"); export={};features={};audit=defaultdict(int)
    for sh in range(8):
        counts=load(M/f"graphs-{sh}.json.gz");orders=load(M/f"orders-{sh}.json.gz");assert sha(M/f"graphs-{sh}.json.gz")==seal[f"graphs-{sh}.json.gz"] and sha(M/f"orders-{sh}.json.gz")==seal[f"orders-{sh}.json.gz"]
        lookup={(q,c):s["M"] for q,t,c,s in orders if t in targets}; by=defaultdict(list)
        parent=l.ref.TR/f"forecasts-main-{sh}.json.gz";assert sha(parent)==rawplan["parents"][parent.relative_to(W).as_posix()]
        for row in load(parent):
            if row["t"] in targets:by[row["t"]].append(row)
        raw=l.env.RAW/f"trajectories-{sh:05d}.jsonl";hasher=hashlib.sha256()
        with raw.open("rb") as rawf:
            for buf in rawf:
                hasher.update(buf);tok=re.search(rb'"session_id"\s*:\s*"(traj_[^"]+)"',buf[:1200]);assert tok
                t=tok.group(1).decode()
                if t not in by:continue
                obj=json.loads(buf);fp,hh=idx[t];assert sha(fp)==hh;rec=load(fp)
                assert hashlib.sha256(buf.rstrip(b"\r\n")).hexdigest()==rec["raw_source"] or hashlib.sha256(buf).hexdigest()==rec["raw_source"]
                tr=l.parent.adapt_isetrace_record(l.parent.parse_isetrace_record(obj),source_revision=l.env.pilot.RAW[1]);ids,geom=l.geometry(rec); first,groups=l.parent.lookup(tr,rec,ids,geom);ns=list(ids);unit={n:i for i,n in enumerate(sorted(ns))}
                call_list=sorted(groups); gids={c:i for i,c in enumerate(call_list)};memb=defaultdict(list);Mby=defaultdict(list); times={e.call_id:k for k,e in enumerate(tr.events) if e.event_type=="tool_output"}
                for n in rec["g"]["nodes"]:
                    name=n["node_id"]
                    if name in ids and n["kind"]==l.ref.OUTPUT_CHUNK_NODE:
                        c=n["attributes"]["call_id"];assert first[ids[name]]==times[c];memb[gids[c]].append(unit[name]);Mby[c].append(name)
                life=oracle.windows(tr.events);links=[];excluded_equal=0;excluded_early=0
                for (a,b),(v,end,_,_) in life.items():
                    if a not in gids or b not in gids:continue
                    assert max(times[a],times[b])==v
                    if v<end:links.append([gids[a],gids[b],v])
                    elif v==end:excluded_equal+=1
                    else:excluded_early+=1
                done=set();fit=l.FeedIndex();historic=set();cuts=l.parent.cuts_for(tr.events);probes=[];rs=[];rr={n["node_id"]:n for n in by[t][0]["rr"]};native_ref={v[0]:v for v in expected_native[t]["states"]} if t in expected_native else {}
                for step,e in enumerate(tr.events):
                    fit.consume(e)
                    if e.event_type=="tool_output":done.add(e.call_id)
                    edges={(a,b) for x,y in fit.support if x in done and y in done for a in Mby[x] for b in Mby[y]};historic.update(edges)
                    if step in native_ref:
                        assert hashobj(sorted(historic))==native_ref[step][4];audit["native_prefix"]+=1
                    if step not in cuts:continue
                    pairs=sorted((unit[a],unit[b]) for a,b in historic);deg=degrees(pairs); II=np.flatnonzero(first<=step);_,gg=l.parent.truncate(geom,II,fit,groups);nodes=[ns[k] for k in II];rev={n:i for i,n in enumerate(nodes)}
                    X,cost=l.features(nodes,gg["exact"],rr);X[:,[11,12,19,20]]=0
                    qs=[]
                    for r in by[t]:
                        av=[j for j,z in enumerate(r["rr"]) if z["node_id"] in rev];pm=[rev[r["rr"][j]["node_id"]] for j in av];qs.append([av,pm])
                    for pct,at in zip((25,50,75,100),cuts):
                        if at!=step:continue
                        ref=counts[t]["states"][str(pct)];assert len(pairs)==ref["material"]==survival[t][str(pct)]["pu_pairs"]["M"]
                        callcheck={(x,y) for x,y in life if life[(x,y)][0]<=step and life[(x,y)][0]<life[(x,y)][1]};assert hashobj(sorted(callcheck))==survival[t][str(pct)]["identities"]["M"]
                        probes.append({"cut":pct,"at":step,"count":len(pairs),"pairs":hashobj(pairs),"degrees":hashobj(deg)})
                        want=[hashobj(lookup[r["q"],pct]) for r in by[t]];rs.append({"cut":pct,"units":[unit[n] for n in nodes],"x":X.tolist(),"cost":cost.tolist(),"q":qs,"wanted":want});audit["history_cuts"]+=1
                assert len(probes)==4;export[ix[t]]={"groups":[[g,sorted(v)] for g,v in sorted(memb.items())],"first":sorted(links),"checks":probes,"at_boundary":excluded_equal,"before_boundary":excluded_early}
                features[ix[t]]=rs
        assert hasher.hexdigest()==rawplan["raw"][raw.name];print("shard",sh,len(export),flush=True)
    assert len(export)==len(tids);save(D/"input.json.gz",export);save(D/"reader-checks.json.gz",features);audit.update({"histories":len(tids),"primary":len(primary),"native":len(native)})
    save(D/"extraction.json",{"checks":dict(audit),"input":sha(D/"input.json.gz"),"reader":sha(D/"reader-checks.json.gz"),"plan":sha(D/"plan.json")})
if __name__=="__main__":run()
