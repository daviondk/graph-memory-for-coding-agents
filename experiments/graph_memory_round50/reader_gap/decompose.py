"""Decompose a paired answer-quality contrast by changes in support and answer visibility."""
from collections import defaultdict,Counter
import gzip,hashlib,json
from pathlib import Path
D=Path(__file__).resolve().parent
SRC=D.parent/"semantic_address"
def signed(name):
    file=SRC/name;raw=file.read_bytes()
    assert hashlib.sha256(raw).hexdigest()==json.loads((SRC/"manifest.json").read_bytes())["files"][name]
    return json.loads(gzip.decompress(raw))
def summarize(rows,total):
    delta=[r[1][1]-r[0][1] for r in rows]
    return dict(n=len(rows),f1_before=sum(r[0][1] for r in rows)/len(rows),f1_after=sum(r[1][1] for r in rows)/len(rows),
        gains=sum(d>0 for d in delta),losses=sum(d<0 for d in delta),ties=sum(d==0 for d in delta),
        delta_f1_pp=100*sum(delta)/len(rows),net_contribution_pp=100*sum(delta)/total)
def calculate():
    data=signed("outcomes.json.gz");orders=signed("orders.json.gz");ctx=signed("contexts.json.gz")
    ans={}
    for name,baseline,intervention in (("dense","dense","linked_dense"),("lexical","lex","true")):
        groups=defaultdict(list);allrows=[];unchanged=0
        for q,v in data.items():
            a,b=(v["arms"][key] for key in (baseline,intervention))
            same=orders[q][baseline]==orders[q][intervention]
            assert a[5]==b[5]
            if same:
                assert ctx[q]["refs"][baseline][1]==ctx[q]["refs"][intervention][1] and a==b
                unchanged+=1
            else:
                for label,i in (("full_support",2),("answer_string",3)):
                    s=("up" if b[i]>a[i] else "down" if b[i]<a[i] else f"same_{a[i]}")
                    groups[label,s].append((a,b))
                groups["changed","all"].append((a,b))
                groups["type",v["kind"]].append((a,b))
            allrows.append((a,b))
        assert unchanged+len(groups["changed","all"])==len(data)==640
        overall=summarize(allrows,len(data));partition={}
        for (label,change),rows in groups.items():
            partition.setdefault(label,{})[change]=summarize(rows,len(data))
        for kind in ("full_support","answer_string","type"):
            assert abs(sum(z["net_contribution_pp"] for z in partition[kind].values())-overall["delta_f1_pp"])<1e-9
        ans[name]=dict(same_address=unchanged,all=overall,groups=partition)
    return ans
if __name__=="__main__":
    r=calculate()
    (D/"results.json").write_text(json.dumps(r,sort_keys=True,indent=2)+"\n",encoding="utf8")
    for a,v in r.items():
        for k in ('full_support','answer_string'):
            print(a,k,{name:(b['n'],b['gains'],b['losses'],round(b['net_contribution_pp'],3)) for name,b in v['groups'][k].items()})

