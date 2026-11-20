"""Rebuild agent-visible results from MCP receipts and check independent frozen target hashes."""
import gzip,hashlib,json,re,sys
from pathlib import Path
D=Path(__file__).resolve().parent;OLD=D.parent/"ledger"
sys.path.insert(0,str(OLD));from audit import decode
def load(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def h(b):return hashlib.sha256(b).hexdigest()
def get(r):return "\n".join(v["text"] for v in r["response"]["result"]["content"] if v["type"]=="text")
def main():
    truths={"controlled|"+r["case"]:(r["old_sha"],r["new_sha"]) for r in load(OLD/"pair_states.json")}
    truths.update({"released|"+str(i):(r["sha_old"],r["sha_new"]) for i,r in enumerate(load(OLD/"natural/released_pairs.json.gz")) if r["new"] is not None})
    out={}
    for fs in ("ext4","tmpfs"):
        archive=load(D/fs/"native_calls.json.gz")
        base={};delivered={};burst=[];checked=0
        for r in archive:
            k=(r["arm"],r["filename"])
            old=base.get(k,b"");txt=get(r)
            full=decode(txt,old);base[k]=full
            if r["case"].startswith("burst|"):
                burst.append((r["case"],r["arm"],h(full)));continue
            target=truths[r["case"]]
            if r["stage"]=="original":assert h(full)==target[0]
            else:delivered[r["case"],r["arm"]]=h(full)
            checked+=1
        for r in load(D/fs/"metrics.json.gz"):
            case=r["panel"]+"|"+r["case"];k=(case,r["arm"]);a,b=truths[case]
            assert a==r["before"] and b==r["truth"]
            if r["hit"]:assert k not in delivered and r["actual"]==a
            else:assert delivered[k]==r["actual"]
        stress=load(D/fs/"stress.json.gz");eligible=[r for r in burst if len(r[0].split("|"))==3]
        observed={(s["repo"],s["mode"],s["i"],s["arm"]):s for s in stress}
        repos=["pallets__click","python-attrs__attrs","HypothesisWorks__hypothesis","yaml__pyyaml"]
        actual_order=[]
        for r in load(OLD/"pair_states.json"):
            repo=r["fixture"].split("/")[1]
            if repo not in actual_order and r["index"]%3==0:actual_order.append(repo)
        assert set(repos)==set(actual_order)
        for label,arm,digest in eligible:
            _,name,i=label.split("|");m=re.fullmatch(r"burst_(\d+)_(.+)\.py",name)
            s=observed[actual_order[int(m[1])],m[2],int(i),arm]
            assert digest==s["visible_sha"] and not s["hit"]
        out[fs]={"non_burst_receipts":checked,"reconciled_metrics":len(load(D/fs/"metrics.json.gz")),
                 "validated_burst_real_responses":len(eligible),"burst_outcomes":len(stress)}
    (D/"verification.json").write_text(json.dumps(out,indent=1));print(out)
if __name__=="__main__":main()
