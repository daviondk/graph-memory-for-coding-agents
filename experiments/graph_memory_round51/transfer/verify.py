"""Independent, offline checks of address choice, equal prompt budgets and official answer scoring."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import re
import string
import struct

HERE = Path(__file__).resolve().parent

def read(name):
    data = (HERE/name).read_bytes()
    return json.loads(gzip.decompress(data) if name.endswith(".gz") else data)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def normalized(text):
    s = text.lower().translate(str.maketrans("", "", string.punctuation))
    return " ".join(re.sub(r"\b(a|an|the)\b"," ",s).split())

def answer_metrics(pred, gold):
    p,g=normalized(pred),normalized(gold)
    exact=float(p==g)
    u,v=p.split(),g.split()
    common=sum((Counter(u)&Counter(v)).values())
    if common==0 or (p!=g and ({p,g} & {"yes","no","noanswer"})):
        return exact,0.
    return exact,2*common/(len(u)+len(v))

def verify():
    contracted = read("threshold-seal.json")["primary"]
    assert contracted == 0.04178261756896973
    panel, orders = read("panel.json"), read("orders.json.gz")
    obs, prompts = read("contexts.json.gz"), read("prompts.json.gz")
    answers = read("answers.json.gz")
    outcomes, gold = read("outcomes.json.gz"), read("gold.json.gz")
    metrics = read("results.json")
    assert len(panel["order"]) == len(set(panel["order"])) == len({x["cluster"] for x in obs.values()}) == 640
    assert set(panel["order"]) == set(obs) == set(outcomes) == set(gold) == set(orders)
    assert set(answers) == set(prompts)
    for k,ts in prompts.items():
        assert hashlib.sha256(struct.pack(f"<{len(ts)}I",*ts)).hexdigest() == k
    tail = read("reader-boundaries.json")["tail"]
    arms = ["dense","adaptive","linked_dense"]
    sums = {a:[0.]*4 for a in arms}
    differences = []
    costs = read("timing-events.json.gz")
    assert {r[0] for r in costs if not r[1]}==set(prompts) and len([r for r in costs if not r[1]])==len(prompts)
    for q in panel["order"]:
        row,c,g=orders[q],obs[q],gold[q]
        ranks=row["order"]
        assert len(ranks)==len(set(ranks)) and row["seed"] not in ranks
        v = {int(k):score for k,score in row["scores"].items()}
        assert set(v)==set(ranks) and all(v[x]>=v[y] for x,y in zip(ranks,ranks[1:]))
        linked = next((i for i in ranks if i in row["edges"]),ranks[0])
        chosen={"dense":ranks[0],"linked_dense":linked,"adaptive":linked if v[ranks[0]]-v[linked]<=contracted else ranks[0]}
        seqs=[]
        for a, idx in chosen.items():
            assert idx==row[a]==c["refs"][a][0]
            _,k,plen = c["refs"][a]
            ts=prompts[k]
            assert len(ts)==plen and ts[-len(tail):]==tail
            seqs.append(ts)
            match, f1 = answer_metrics(answers[k]["answer"],g["answer"])
            read_titles={g["titles"][c["seed"]],g["titles"][idx]}
            gold_titles=set(g["support_titles"])
            values=[match,f1,float(gold_titles<=read_titles),len(gold_titles & read_titles)/len(gold_titles)]
            assert all(abs(x-y)<1e-12 for x,y in zip(values,outcomes[q]["arms"][a],strict=True))
            for j,w in enumerate(values):sums[a][j]+=w
        prefix=len(seqs[0])-len(tail)-c["n"]
        assert len({len(ts) for ts in seqs})==1 and all(ts[:prefix]==seqs[0][:prefix] for ts in seqs)
        differences.append(outcomes[q]["arms"]["adaptive"][1]-outcomes[q]["arms"]["dense"][1])
    for a,ls in sums.items():
        assert all(abs(x/640-y)<1e-10 for x,y in zip(ls,metrics["means"][a],strict=True))
    sig=read("signflip-new.json")
    assert sum(x>0 for x in differences)==sig["wins"] and sum(x<0 for x in differences)==sig["losses"]
    assert abs(100*sum(differences)/640-sig["pp"])<1e-10
    for k,v in read("replay.json").items():assert answers[k]==v
    print(f"Verified all {len(orders)} selections for each of three arms, {len(prompts)} input hashes, 1,920 official-equivalent answer and support scores and {len(costs)} timing events.")

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--manifest",action="store_true")
    args=parser.parse_args()
    if args.manifest:
        files=read("SHA256.json")
        assert all(sha(HERE/name)==h for name,h in files.items())
        assert set(files)=={p.name for p in HERE.iterdir() if p.is_file() and p.name!="SHA256.json"}
    verify()
