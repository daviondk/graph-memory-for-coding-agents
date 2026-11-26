"""Hash benchmark identities and blind textual pointers, never publish source text."""
from pathlib import Path
from collections import Counter
import gzip,hashlib,json,re,unicodedata
HERE=Path(__file__).resolve().parent;W=HERE.parents[1]
SCALE=HERE.parent/"calibration_scale";OFF=W/"graph_memory_round22/native_multiseed/official580"
RAW=Path("D:/CodexResearch/x20-isetrace-runtime/inputs")
def digest(x):return hashlib.sha256(x.encode() if isinstance(x,str) else x).hexdigest()
def norm(x):return " ".join(unicodedata.normalize("NFKC",x).casefold().split())
def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(",",":"))
def get(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def save(p,v):
    b=(canonical(v)+"\n").encode();p.write_bytes(gzip.compress(b,mtime=0) if p.suffix==".gz" else b)
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def visible(messages):
    return [{"role":m["role"],"content":m.get("content"),"name":m.get("name"),
        "tools":[c.get("function",{}) for c in m.get("tool_calls",[]) or []]} for m in messages]
def main():
    parts=get(OFF/"split.json.gz");tags={r["q"]:(k,r["t"]) for k,rr in parts.items() for r in rr};tids={t for _,t in tags.values()}
    qbase=RAW/"query-authoring/isetrace-v7-raw.jsonl";mfile=qbase.with_suffix(".jsonl.metadata.jsonl")
    meta={r["query_id"]:r for r in map(json.loads,mfile.open(encoding="utf8"))};qs={};ts={};rawq=0;bad=0
    for r in map(json.loads,qbase.open(encoding="utf8")):
        rawq+=1;q=r["id"]
        if q not in tags:continue
        m=meta[q];sp,t=tags[q];assert t==m["trajectory_id"] and q not in qs
        refs=[x["quote"] for x in r["gold"]];sources=[x["source"] for x in r["gold"]]; assert all(refs)
        qs[q]={"s":sp,"t":t,"task_key":digest(m["task_key"]),"query":digest(r["query"]),"query_norm":digest(norm(r["query"])),
            "packet":digest(r["text"]),"packet_norm":digest(norm(r["text"])),"gold_quotes":sorted(set(map(digest,refs))),
            "gold_norm":sorted({digest(norm(x)) for x in refs}),"sources":[digest(t+"|"+s) for s in sources],"mode":m["memory_mode"]}
    hashes={qbase.name:sha(qbase),mfile.name:sha(mfile)};count=0
    for p in sorted((RAW/"trajectories").glob("*.jsonl")):
        h=hashlib.sha256()
        with p.open("rb") as f:
            for line in f:
                count+=1;h.update(line);m=re.search(rb'"session_id"\s*:\s*"(traj_[^"]+)"',line[:1000])
                if m and m.group(1).decode() not in tids:continue
                row=json.loads(line);t=row["session_id"]
                if t not in tids:continue
                assert t not in ts;ms=row["messages"]; intents=row["source_intents"]; literals=[v["natural_language_intent"] for v in intents]
                if not literals:bad+=1
                texts=sorted({digest(norm(v)) for v in literals if norm(v)})
                ts[t]={"transcript":digest(canonical(ms)),"visible_transcript_norm":digest(norm(canonical(visible(ms)))),
                    "intent_ids":sorted(set(map(digest,row["source_intent_ids"]))),"intent_norm":texts,"intent_set":digest(canonical(texts)) if texts else None,
                    "utterances":[digest(norm(m["content"])) for m in ms if m.get("role")=="user" and isinstance(m.get("content"),str) and norm(m["content"])]}
        hashes[p.name]=h.hexdigest()
    assert qs.keys()==tags.keys() and ts.keys()==tids
    save(HERE/"identities.json.gz",{"q":qs,"t":ts})
    save(HERE/"input.json",{"official":sha(OFF/"split.json.gz"),"identity":sha(HERE/"identities.json.gz"),"sources":hashes,"raw_trajectories":count,"raw_queries":rawq,"missing_intents":bad,"protocol":sha(HERE/"PROTOCOL_RU.md"),"code":sha(Path(__file__))})
    print(count,len(qs),len(ts),bad,flush=True)
if __name__=="__main__":main()
