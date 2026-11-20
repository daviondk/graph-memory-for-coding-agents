"""Run 21 unique requests immediately with the unchanged reader, then join the 171 actually identical responses."""
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from infer import D, read, save, sha, from_str

def expected(row):
    k=row["id"];snippet=row["snippets"]["ast_witness"][0]
    user="External Java fragment:\n"+snippet+"\n\nLast lines of current file:\n"+row["ctx"]+"\n\nNext source line:"
    return dict(model="qwen38-27b-ud-q4km",messages=[dict(role="system",content="Complete the next nonempty source line in the current Java file. Output exactly one line of Java. Use the external fragment when relevant. No explanation or Markdown."),dict(role="user",content=user)],
                temperature=0,seed=int(sha("r4java|"+k)[:7],16),max_tokens=80,repeat_penalty=1,cache_prompt=False,stream=False,chat_template_kwargs={"enable_thinking":False})

def local(p,obj):
    s=from_str(obj).encode()
    p.write_bytes(gzip.compress(s,mtime=0) if p.suffix==".gz" else s)

def main():
    rows=read("G_packets.json.gz");ids={r["id"]:r for r in rows}
    reuse=read("G_reuse_plan.json"); novel={r["id"] for r in reuse if not r["same_as"]}
    stage=D/"G_fresh";stage.mkdir(exist_ok=True)
    shutil.copyfile(D/"G_PROTOCOL_RU.md",stage/"PROTOCOL_RU.md")
    shutil.copyfile(D/"infer.py",stage/"infer.py")
    local(stage/"G_packets.json.gz",[row for row in rows if row["id"] in novel])
    local(stage/"G_data_lock.json",{"root_G_data_lock_sha":sha((D/"G_data_lock.json").read_bytes()),"fresh_rows":len(novel),
                                 "G_packets_sha":sha((stage/"G_packets.json.gz").read_bytes()),"same_infer_sha":sha((stage/"infer.py").read_bytes())})
    print("Starting",len(novel),"new GPU queries using SHA-identical infer.py G",flush=True)
    subprocess.run([sys.executable,"-u",str(stage/"infer.py"),"G"],cwd=stage,check=True)
    print("New answers sealed, waiting for A/B identical physical requests",flush=True)
    while not all((D/(s+"_decisions.json")).is_file() for s in ("A","B")): time.sleep(5)
    plans={k: read(k+"_assignment.json") for k in ("A","B")}
    seals={k: read(k+"_decisions.json") for k in ("A","B")}
    stage_plan=json.loads((stage/"G_assignment.json").read_bytes()); stage_manifest=json.loads((stage/"G_decisions.json").read_bytes())
    dest=D/"G_calls";dest.mkdir(exist_ok=True)
    ledger={}
    for row in reuse:
        id_=row["id"];p=ids[id_]; req=expected(p); cid=sha(from_str(req)); name=cid+".json.gz"
        if id_ in novel:
            assert stage_plan[id_]["ast_witness"]==cid
            src=stage/"G_calls"/name; checksum=stage_manifest[name];source="G_fresh"
        else:
            source=row["source_panel"]
            key_set={plans[source][id_][a] for a in row["same_as"]}
            assert key_set=={cid}
            src=D/(source+"_calls")/name;checksum=seals[source][name]
        data=src.read_bytes()
        assert sha(data)==checksum and json.loads(gzip.decompress(data))["request"]==req
        target=dest/name
        if target.exists():assert target.read_bytes()==data
        else:target.write_bytes(data)
        ledger[id_]={"from":source,"cid":cid,"response_sha":checksum}
    save("G_reuse_receipt.json",ledger)
    print("All 192 verified inputs; finalizing the full panel",flush=True)
    subprocess.run([sys.executable,"-u",str(D/"infer.py"),"G"],cwd=D,check=True)
    print("Final G_decisions recorded",flush=True)
if __name__=="__main__":main()
