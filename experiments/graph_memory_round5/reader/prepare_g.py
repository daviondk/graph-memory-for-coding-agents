"""Verify and present use-site evidence. All inputs are visible context; no target columns are accessed."""
from collections import Counter,defaultdict
import datetime
import hashlib
import json
import sys
from pathlib import Path
import pyarrow.parquet as pq
from evidence import query, local_view, proximity, pp, trim
from infer import D, read, save

REVIEW=D.parent/"review"
SOURCE=D.parents[1]/"graph_memory_round4/repo/archive_inputs"


def digest(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()


def main():
    supply=json.loads((REVIEW/"witness_supply.json").read_bytes())["items"]
    panel={s:read(s+"_packets.json.gz") for s in ("A","B")}
    groups=defaultdict(list)
    for s,rows in panel.items():
        for r in rows:groups[r["file"]].append((s,r))
    output=[];decision=[]; reasons=Counter()
    for name,group in groups.items():
        need={r["local_index"] for s,r in group};cache={};offset=0
        for batch in pq.ParquetFile(SOURCE/name).iter_batches(columns=["context"],batch_size=64):
            for j in need:
                if offset<=j<offset+len(batch):cache[j]=batch.column(0)[j-offset].as_py()
            offset+=len(batch)
        for s,r in group:
            z=supply[s][r["id"]]; event=r["edge_event"]
            changed=None
            if z["previous_direct"]:
                sn=r["snippets"]["edge"]; reason="reuse_existing_direct"
            elif not z["available"]:
                sn=r["snippets"]["local"]; reason="use_local"
            else:
                sources={int(k):v for k,v in z["available"].items()}
                previous=event["source"] if event is not None else None
                ix=previous if previous in sources else min(sources,key=lambda a:sources[a]["graph_rank"])
                ctx,candidates=r["ctx"],cache[r["local_index"]]
                q=query(ctx); lines=candidates[ix].splitlines()
                def score(j):
                    prior=pp("\n".join(lines[max(0,j-3):j]))
                    return proximity(q,prior)+.3*proximity(q,pp(lines[j])),-j
                row=max({j for j,role in sources[ix]["uses"]},key=score)
                witness=trim(lines[row].strip()+"\n"+"\n".join(lines[row+1:row+3]),100)[0]
                decl=local_view(q,candidates[r["rank"][0]],145)[0]
                sn=trim(decl+"\n// Usage in another fragment\n"+witness,256)
                reason="new_line_same_source" if previous==ix else "new_source_and_line"
                changed={"source":ix,"line":row}
            assert sn[1]<=256
            output.append({k:v for k,v in r.items() if k not in ("snippets","edge_event")}|{"snippets":{"ast_witness":sn},
                          "source_panel":s,"policy_reason":reason,"new_witness":changed})
            matches=[a for a,(t,n) in r["snippets"].items() if t==sn[0]]
            reasons[s,reason]+=1
            decision.append({"id":r["id"],"source_panel":s,"same_as":matches,"reason":reason,"new_witness":changed})
    assert len(output)==len({r["id"] for r in output})==192
    save("G_packets.json.gz",sorted(output,key=lambda x:x["id"]))
    save("G_reuse_plan.json",decision)
    lockfiles=[D/"G_packets.json.gz",D/"G_reuse_plan.json",D/"G_PROTOCOL_RU.md",Path(__file__),D/"infer.py",D/"evidence.py",
               D/"A_data_lock.json",D/"B_data_lock.json",REVIEW/"witness_supply.json",REVIEW/"witness_supply.py",REVIEW/"ast_roles.json"]
    save("G_data_lock.json",{"utc":datetime.datetime.now(datetime.UTC).isoformat(),"sha":{str(z.relative_to(D.parent)):digest(z) for z in lockfiles},
                             "n":len(output),"counts":{s:{key:n for (p,key),n in reasons.items() if p==s} for s in panel},
                             "novel":sum(not r["same_as"] for r in decision),"old_decisions_status":{s:(D/(s+"_decisions.json")).exists() for s in ("A","B","C","F")}})
    print(read("G_data_lock.json"))
if __name__=="__main__":main()
