"""Independently enumerate physical deletions over the prefix and compare to every reported outcome."""
from collections import defaultdict
from statistics import mean
from hashlib import sha256
from math import isclose
from inventory import P,D,get,save
SCEN = ["no_loss","one_message","one_worker","first_message","shared_source"]
def audit(p):
    prefs={r["id"]:r["events"] for r in get(P/(p+"-prefix.json.gz"))};targets={r["id"]:r["future"] for r in get(P/(p+"-targets.json.gz"))};results=get(D/(p+"-per-case.json.gz"));seen={};n=0
    file_map={k["key"]:k for k in get(P/"base-source-map.json")} if p=="swe" else {};files={};nverify=0
    digest=lambda z:sha256(z.encode()).hexdigest()
    for row in results:
        q=row["id"]
        if q not in seen:
            ev=prefs[q];domains=[v["w"] for v in ev];index=defaultdict(list);before=[]
            for i,e in enumerate(ev):
                for path,lines in e["r"]:
                    if len(lines)>=2:before.append((path,lines[0],lines[-1]))
                    for l,d,b in lines:
                        bucket=index[path,l,d]
                        if i not in bucket:bucket.append(i)
            seen[q]=(ev,domains,index,before)
        ev,domains,index,before=seen[q]
        def endpoints(v):return [(v[0],l,d) for l,d,b in v[1:]]
        probes=before if row["set"]=="prefix" else [v for v in targets[q] if row["set"]=="future" or all(key in index for key in endpoints(v))]
        assert len(probes)==row["n"];n+=len(probes)
        for a,reported in row["arms"].items():
            sums=[0.]*5
            for v in probes:
                xy=endpoints(v);original=[index.get(u,[]) for u in xy]
                if a=="direct_base_snapshot":
                    path=v[0]
                    if path not in files:
                        b=(P/"base"/path).read_bytes();assert sha256(b).hexdigest()==file_map[path]["sha"];files[path]=b.decode("utf8").splitlines()
                    for _,l,d in xy:assert digest(files[path][l-1])==d;nverify+=1
                    vals=[1.,1.,1.,1.,0.]
                else:
                    dep=[]
                    for ids in original:
                        if not ids:dep.append([]);continue
                        if a=="one":sel=ids[:1]
                        elif a=="full":sel=ids
                        elif a=="first_two":sel=ids[:2]
                        elif a=="latest":sel=ids[:1]+ids[-1:]
                        else:
                            alt=next((i for i in ids[1:] if domains[i]!=domains[ids[0]]),None);sel=ids[:2] if alt is None else [ids[0],alt]
                        dep.append(sel)
                    def check(drop):return float(all(any(i not in drop for i in group) for group in dep))
                    carrier=original[0][:1]
                    vals=[check([]),mean(check([i]) for i in range(len(ev))),mean(check([i for i,d in enumerate(domains) if d==w]) for w in set(domains)),check(carrier),0.]
                for j,x in enumerate(vals):sums[j]+=x
            assert all(isclose(v/len(probes),r,abs_tol=2e-13) for v,r in zip(sums,reported)),(q,a,sums,reported)
    return dict(case_subsets=len(results),pair_checks=n,base_quote_byte_checks=nverify,base_files_verified=len(files),joint_loss_scenarios=SCEN)
if __name__=="__main__":
    for p in ("swe","ise"):
        res=audit(p);save(D/(p+"-audit.json"),res);print(p,res)

