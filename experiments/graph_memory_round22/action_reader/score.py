"""Match the actual selected producer IDs to versioned recorded inputs after the inference seal."""
from collections import defaultdict
import json
import sqlite3
import numpy as np
from prepare import D,C,OBS,LETTERS,read,h,write

def compare(rows,a,b):
    gr=defaultdict(list)
    for r in rows:gr[r["family"]].append(float(r["arms"][a])-float(r["arms"][b]))
    sums=np.array([sum(v) for v in gr.values()]);counts=np.array([len(v) for v in gr.values()])
    rng=np.random.default_rng(22021);ids=rng.integers(0,len(gr),size=(10000,len(gr)))
    boots=sums[ids].sum(axis=1)/counts[ids].sum(axis=1)
    ds=[d for group in gr.values() for d in group]
    return dict(estimate=sum(ds)/len(ds),cluster_ci95=np.quantile(boots,[.025,.975]).tolist(),wins=sum(v>0 for v in ds),
                losses=sum(v<0 for v in ds),ties=sum(v==0 for v in ds),families=len(gr))

def main():
    forecasts=D/"choices.json.gz";receipt=read(D/"reader-lock.json");assert receipt["responses"]==h(forecasts.read_bytes())
    result=read(forecasts);rows=read(D/"cards.json.gz");assert read(D/"selection-lock.json")["cards"]==h((D/"cards.json.gz").read_bytes())
    # The chosen action executes one indexed lookup in the archive; returned normalized outputs are hashed.
    archive=sqlite3.connect(":memory:")
    archive.execute("CREATE TABLE event(t TEXT,id INTEGER,writes BLOB NOT NULL,PRIMARY KEY(t,id)) WITHOUT ROWID")
    for r in read(C/"flow-packets.json"):
        archive.executemany("INSERT INTO event VALUES(?,?,?)",[(r["trace"],e["id"],json.dumps(e["write"],separators=(",",":")).encode()) for e in r["events"] if e["write"]])
    archive.commit();archive.execute("PRAGMA query_only=ON")
    lookups=0
    gold=defaultdict(set)
    for t in read(C/"flow-gold.json"):
        for r in t["reads"]:gold[t["trace"],r["consumer"]].add(r["producer"])
    out=[]
    for row in rows:
        target=gold[row["t"],row["step"]];arms={};picks={};positions={};reads={};tokens={}
        for arm,r in row["arms"].items():
            cards=r["cards"]
            for direction,msg in r["prompts"].items():
                x=cards if direction=="normal" else cards[::-1]
                letter=result[msg]["letter"];p=x[LETTERS.index(letter)]["producer"]
                record=archive.execute("SELECT writes FROM event WHERE t=? AND id=?",(row["t"],p)).fetchone()
                assert record and len(json.loads(record[0]))>0
                reads[arm+"/"+direction]=h(record[0]);tokens[arm+"/"+direction]=result[msg]["usage"]["prompt_tokens"];lookups+=1
                arms[arm+"/"+direction]=int(p in target);picks[arm+"/"+direction]=p;positions[arm+"/"+direction]=letter
            arms[arm+"/rule"]=int(r["rule"] in target)
            arms[arm+"/available"]=int(any(c["producer"] in target for c in cards))
            arms[arm+"/random_expected"]=sum(c["producer"] in target for c in cards)/len(cards)
        out.append({"case":row["case"],"family":row["family"],"n_targets":len(target),"arms":arms,"actions":picks,"letters":positions,"returned_write_hashes":reads,"input_tokens":tokens})
    eligible=[r for r in out if r["n_targets"]]
    write(D/"outcomes.json.gz",out)
    def summary(part):
        return {"n":len(part),"families":len({r["family"] for r in part}),"hits_or_random_expected":{k:sum(r["arms"][k] for r in part) for k in part[0]["arms"]},
               "primary":compare(part,"name_index/normal","fifo/normal"),"versus_rule":compare(part,"name_index/normal","name_index/rule"),
               "reversed":compare(part,"name_index/reverse","fifo/reverse"),
               "qwen_selected_same_source_when_reversed":{a:sum(r["actions"][a+"/normal"]==r["actions"][a+"/reverse"] for r in part) for a in ("fifo","name_index")}}
    totals={"selected_before_labels":len(out),"positive":summary(eligible),"all_descriptive":summary(out),"n_without_reference":len(out)-len(eligible),
            "families_before":len({r["family"] for r in out}),"source":h((D/"reader-lock.json").read_bytes()),"gold_sha256":h((C/"flow-gold.json").read_bytes()),
            "per_query":h((D/"outcomes.json.gz").read_bytes()),"code":h(D.joinpath("score.py").read_bytes())}
    totals["executed_indexed_lookups"]=lookups
    totals["mean_prompt_tokens_normal"]={a:float(np.mean([r["input_tokens"][a+"/normal"] for r in out])) for a in ("fifo","name_index")}
    write(D/"results.json",totals);print(json.dumps(totals["positive"]),flush=True)
if __name__=="__main__":main()
