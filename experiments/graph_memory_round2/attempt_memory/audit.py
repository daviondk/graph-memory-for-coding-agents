"""Independent joins using candidate file hashes, enhanced-test receipts and sealed choices."""
import collections, gzip, hashlib, json
from pathlib import Path
from score import contrast
from prepare import HERE,read,save,sha
def main():
    total={}
    for panel in ("old","fresh"):
        main_rows=read(HERE/f"item_scores_{panel}.json")
        strong={v["id"]:v for v in read(HERE/f"strong_{panel}.json")}
        obs={v["id"]:v for v in read(HERE/f"observed_{panel}.json")}
        assert len(strong)==len(main_rows)==len(obs)
        output=[];eligible=0;cost=collections.Counter()
        for r in main_rows:
            i=r["id"];s=strong[i];receipts=read(HERE/f"grading/{i}/receipt.json");trace=obs[i]
            for j,a in enumerate(trace["arms"]):
                raw=(HERE/f"programs/{i}/{j}.py").read_bytes()
                assert sha(raw)==receipts[str(j)]["sha256"]
            solved={a:int(receipts[str(j)]["status"]=="pass") for a,j in {**r["arms"],"direct":s["direct"],"mbr":s["mbr"]}.items()}
            assert all(solved[a]==r["hit"][a] for a in r["arms"])
            if s["call"]:
                key=s["call"]; call=json.loads(gzip.decompress((HERE/f"calls/{key}.json.gz").read_bytes()))
                assert s["usage"]==call["reply"]["usage"]
                cost.update({k:v for k,v in s["usage"].items() if type(v)==int});eligible+=1
            output.append(dict(id=i,hit=solved,any_pass=r["hit"]["pool_oracle"],different=bool(r["informative"])))
        save(HERE/f"audited_{panel}.json",output)
        total[panel]=dict(n=len(output),physical_direct_calls=eligible,direct_usage=dict(cost),
          solved={a:sum(x["hit"][a] for x in output) for a in output[0]["hit"]},
          value_minus={a:contrast([r["hit"]["value"]-r["hit"][a] for r in output]) for a in ("direct","mbr")},
          headroom_above_first_public=sum(r["any_pass"]-r["hit"]["first_public"] for r in output))
    records=[json.loads(gzip.decompress(p.read_bytes())) for p in (HERE/"calls").glob("*.gz")]
    total["receipts"]={"n":len(records),"by_system":dict(collections.Counter(r["request"]["messages"][0]["content"][:85] for r in records)),"tokens":{k:sum(r["reply"]["usage"][k] for r in records) for k in ("prompt_tokens","completion_tokens")}}
    save(HERE/"audit.json",total)
if __name__=="__main__":main()
