"""Score full G after its final lock, with original verified targets; quantify actual re-use and newly generated evidence."""
import collections
import datetime
import gzip
import json
from pathlib import Path
import numpy as np
from audit_reader import HERE, READER, check, digest, exact_discordants, idf1, overlap, read, read_responses, similarity_float, source_rows

def method_summary(values):
    return {"correct":sum(v["em"] for v in values),"em_percent":100*sum(v["em"] for v in values)/len(values),
            **{f:sum(v[f] for v in values)/len(values) for f in ("es","id_f1","prompt_tokens","completion_tokens","evidence_tokens")}}

def contrast(rows, baseline):
    n=len(rows)
    if not n:return {"n":0}
    answer={"n":n}
    rng=np.random.default_rng(195526)
    indices=rng.integers(0,n,size=(20000,n))
    for f in ("em","es","id_f1","prompt_tokens","evidence_tokens"):
        d=np.array([float(r["arms"]["G"][f])-r["arms"][baseline][f] for r in rows])
        wins=int((d>0).sum());losses=int((d<0).sum())
        ci=np.quantile(d[indices].mean(axis=1),[.025,.975]).tolist()
        answer[f]={"mean_diff":float(d.mean()),"ci95":ci,"wins":wins,"losses":losses,"p_mcnemar":exact_discordants(wins,losses) if f=="em" else None}
    return answer

def describe(rows):
    methods={a:method_summary([r["arms"][a] for r in rows]) for a in ("G","local","edge","gate")}
    pairs={}
    for a in ("local","edge","gate"):
        pairs[a]={"all":contrast(rows,a),"different_input":contrast([r for r in rows if r["arms"][a]["cid"]!=r["arms"]["G"]["cid"]],a),
                  "new_rows":contrast([r for r in rows if r["source"]=="G_fresh"],a)}
    return {"n":len(rows),"methods":methods,"G_minus":pairs,"reasons":dict(collections.Counter(r["reason"] for r in rows))}

def main():
    info=read(READER/"G_data_lock.json")
    for rel,check_sha in info["sha"].items():
        check(digest(HERE.parent/rel.replace(chr(92),"/"))==check_sha,"G input files")
    packs=read(READER/"G_packets.json.gz"); ledger=read(READER/"G_reuse_receipt.json")
    ix,calls=read_responses("G")
    ab={r["id"]:r for s in ("A","B") for r in read(HERE/f"{s}_audit_items.json.gz")}
    check(set(ix)==set(ledger)==set(ab),"paired identifiers in G")
    ref=source_rows(packs);ast=read(HERE/"ast_roles.json")["records"]
    cases=[]
    for p in packs:
        k=p["id"]; s=p["source_panel"]; cid=ix[k]["ast_witness"]
        raw=ledger[k]
        name=cid+".json.gz";origin=raw["from"]; source_file=(READER/"G_fresh/G_calls" if origin=="G_fresh" else READER/(s+"_calls"))/name
        check(digest(source_file)==raw["response_sha"]==digest(READER/"G_calls"/name) and cid==raw["cid"], "reused response identity")
        prompt,ans,pt,finish,nl,ct=calls[cid];text,n=p["snippets"]["ast_witness"]
        check(prompt=="External Java fragment:\n"+text+"\n\nLast lines of current file:\n"+p["ctx"]+"\n\nNext source line:", "G packet identity")
        gold=ref[k]["next_line"].strip();prior=ab[k]["arms"]
        value={"em":ans==gold,"es":round(similarity_float(ans,gold)),"id_f1":idf1(ans,gold),"cid":cid,"prompt_tokens":pt,"completion_tokens":ct,
               "evidence_tokens":n,"finish":finish,"external":overlap(text,gold)}
        use=ast[s].get(k,{}).get("strong",False)
        cases.append({"id":k,"panel":s,"source":origin,"reason":p["policy_reason"],
                      "arms":{"G":value,"local":prior["local"],"edge":prior["edge"],"gate":prior["edge"] if use else prior["local"]}})
    data={s:describe([r for r in cases if r["panel"]==s]) for s in ("A","B")}
    data["fresh_21_descriptive"]={a:contrast([r for r in cases if r["source"]=="G_fresh"],a) for a in ("local","edge","gate")}
    casespath=HERE/"G_audit_items.json.gz"
    casespath.write_bytes(gzip.compress(json.dumps(cases,sort_keys=True,separators=(",",":")).encode(),mtime=0))
    data.update({"n":len(cases),"new_calls":sum(r["source"]=="G_fresh" for r in cases),"verified_reused":sum(r["source"]!="G_fresh" for r in cases),
                 "cpu_only_gating_reads_real_responses":True,"utc":datetime.datetime.now(datetime.UTC).isoformat(),"script_sha":digest(Path(__file__)),
                 "item_sha":digest(casespath),"sidecar_sha256":digest(READER/"original_targets.json.gz")})
    (READER/"G_results.json").write_text(json.dumps(data,indent=1),encoding="utf8")
    for s in ("A","B"):
        print(s,{a:v["correct"] for a,v in data[s]["methods"].items()},
              {a:v["all"]["em"] for a,v in data[s]["G_minus"].items()})
if __name__=="__main__":main()
