"""Independent audit of equal-slot fixed/adaptive queue budgets and raw held-out completions."""
from collections import Counter,defaultdict
from pathlib import Path
import datetime
import gzip
import json
from itertools import product
from audit_reader import HERE, READER, check, check_files, digest, exact_discordants, idf1, overlap, read, read_responses, similarity_float, source_rows


def main():
    check((READER/"original_targets_receipt.json").is_file(), "target receipt absent")
    lock=read(READER/"F_data_lock.json"); check_files(READER,lock["sha"])
    packets=read(READER/"F_packets.json.gz")
    fixed={p["id"]:p for p in read(READER/"A_packets.json.gz")}
    plans,responses=read_responses("F")
    check(set(plans)==set(fixed)=={p["id"] for p in packets}, "sample equality F to A")
    gold=source_rows(packets)
    items=[];slots=defaultdict(Counter)
    for p in packets:
        k=p["id"]; raw=gold[k]; ref=raw["next_line"].strip()
        check(all(fixed[k][f]==p[f] for f in ("rank","id","local_index","ctx","file","repo")),"rostering")
        arms={}; ds=p["depths"]; b=p["block"]
        check(ds["fixed"]==3 and 1<=ds["budget"]<=8, "slot bounds")
        slots[b].update(ds);slots[b]["n"]+=1
        for a,(snip,snlen) in p["snippets"].items():
            cid=plans[k][a];prompt,answer,tokens,finish,_,out_tokens=responses[cid]
            check(prompt=="External Java fragment:\n"+snip+"\n\nLast lines of current file:\n"+p["ctx"]+"\n\nNext source line:", "F packet")
            arms[a]={"em":answer==ref,"es":round(similarity_float(answer,ref)),"id_f1":idf1(answer,ref),
                     "address_hit":raw["gold_snippet_index"] in p["rank"][:ds[a]],
                     "prompt_tokens":tokens,"completion_tokens":out_tokens,"evidence_tokens":snlen,"cid":cid,"finish":finish,"external":overlap(snip,ref)}
        items.append({"id":k,"arms":arms,"block":b,"depths":ds})
    check(len(slots)==4 and all(x["n"]==32 and x["budget"]==x["fixed"]==96 for x in slots.values()),"per-queue capacity")
    stats={}
    for a in ("budget","fixed"):
        vs=[x["arms"][a] for x in items]
        stats[a]={"em_count":sum(v["em"] for v in vs),"address_hits":sum(v["address_hit"] for v in vs),
                  **{k:sum(v[k] for v in vs)/len(vs) for k in ("es","id_f1","prompt_tokens","evidence_tokens","completion_tokens")}}
    splits={}
    for f in ("em","address_hit"):
        wins=sum(x["arms"]["budget"][f]>x["arms"]["fixed"][f] for x in items)
        losses=sum(x["arms"]["budget"][f]<x["arms"]["fixed"][f] for x in items)
        splits[f]={"wins":wins,"losses":losses,"delta_pp":100*(wins-losses)/len(items),"exact_p":exact_discordants(wins,losses)}
    block_sensitivity = {}
    for metric in ("em","address_hit"):
        deltas = {b:sum(int(v["arms"]["budget"][metric])-int(v["arms"]["fixed"][metric]) for v in items if v["block"] == b) for b in slots}
        null = [sum(m*d for m,d in zip(signs,deltas.values(),strict=True)) for signs in product((-1,1),repeat=len(deltas))]
        p_block = sum(abs(z)>=abs(sum(deltas.values())) for z in null)/len(null)
        block_sensitivity[metric] = {"sum_differences_by_block":deltas,"two_sided_block_sign_flip_symmetry_p":p_block}
    item_path=HERE/"F_audit_items.json.gz"
    item_path.write_bytes(gzip.compress(json.dumps(items,sort_keys=True,separators=(",",":")).encode(),mtime=0))
    out={"n":len(items),"physical_calls":len(responses),"utc":datetime.datetime.now(datetime.UTC).isoformat(),"script_sha":digest(Path(__file__)),
         "methods":stats,"pairs":splits,"per_block":slots,"descriptive_block_sensitivity":block_sensitivity,"per_item_sha":digest(item_path),"target_sidecar_sha256":digest(READER/"original_targets.json.gz")}
    (HERE/"F_audit.json").write_text(json.dumps(out,indent=1),encoding="utf8"); print(out)
if __name__=="__main__":main()

