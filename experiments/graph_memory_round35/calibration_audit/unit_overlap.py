"""Supplemental content-unit audit. Stored external actions are data only."""
from inspect_inputs import *
from collections import defaultdict
POOLROOT=Path("D:/CodexResearch/x20-isetrace-trained/projection/train")
GRAPH=Path("D:/CodexResearch/x20-isetrace-residual/graphs")
DEV=Path("D:/CodexResearch/x20-native-multiseed/official580/dev")
def intersects(span,gold):
    return span["event_id"]==gold["event_id"] and span["json_pointer"]==gold["json_pointer"] and all(x is not None for x in [span["char_start"],span["char_end"],gold["char_start"],gold["char_end"]]) and max(span["char_start"],gold["char_start"])<min(span["char_end"],gold["char_end"])
def main():
    parts=get(OFF/"split.json.gz");train=get(SCALE/"train-inventory.json")["records"];tf={p.name[2:-8]:p for p in GRAPH.glob("*gz")}; sets={}; sourcehash={};test_gold=get(W/"graph_memory_round18/isetrace_official/gold-spans.json.gz"); per={}; pair={}
    all_gold_sets={}; nt=0
    for s,src in [("train",POOLROOT),("dev",DEV),("test",GRAPH)]:
        tall=defaultdict(list)
        for r in parts[s]:tall[r["t"]].append(r["q"])
        prior=set().union(*sets.values()); prev_gold=set().union(*all_gold_sets.values()); svals=set(); sgold=set(); certain=Counter(); raw_units=0
        exp={q:len(v["oof_3894"]) for q,v in get(SCALE/(s+"-orders.json.gz")).items()} if s!="train" else {q:r["n"] for q,r in train.items()}
        file_hash=hashlib.sha256()
        for t,qs in sorted(tall.items()):
            p=src/(t+".json.gz") if s!="test" else tf[t]; file_hash.update((t+"\t"+sha(p)+"\n").encode());z=get(p)
            if s=="train":
                units={n["item_id"]:n for n in z["pool"]}; labels={r["q"]:r["positive"] for r in z["qs"]}
            else:
                units={n["node_id"]:n for n in z["g"]["nodes"] if n["kind"] in {"content.tool_argument","content.tool_output"}}
                labels=z["labels"] if s=="dev" else {q:[i for i,n in units.items() if any(intersects(a,b) for a in n["source_spans"] for b in test_gold[q])] for q in qs}
            assert all(exp[q]==len(units) for q in qs) and set(qs)==set(labels)
            vals={i:digest(norm(n["text"])) for i,n in units.items()}; overlap={v for v in vals.values() if v in prior}; certain["trajectories_with_any_seen_unit"]+=bool(overlap); raw_units+=len(vals)
            certain["seen_pool_unit_instances"]+=sum(v in prior for v in vals.values());svals.update(vals.values())
            for q in qs:
                targ={vals[i] for i in labels[q]};assert targ;sgold.update(targ)
                if s=="test":
                    per[q]={"any_pool_text_seen":bool(overlap),"any_gold_unit_seen_in_prior_pool":bool(targ&prior),"any_gold_unit_seen_in_prior_gold":bool(targ&prev_gold),"all_gold_units_seen_in_prior_pool":targ<=prior}
            nt+=1
        sets[s]=svals;all_gold_sets[s]=sgold; sourcehash[s]=file_hash.hexdigest();pair[s]={"trajectories":len(tall),"units":raw_units,"unique_texts":len(svals),"distinct_gold_text":len(sgold),**certain}
    ret={"by_split":pair,"unique_text_intersections":{},"file_hashes_sorted_by_trajectory":sourcehash,"n_trajectory_files":nt,"test_flags":{k:sum(v[k] for v in per.values()) for k in next(iter(per.values()))}}
    for a,b in [("train","dev"),("train","test"),("dev","test")]:
        ret["unique_text_intersections"][a+"_"+b]={"pool":len(sets[a]&sets[b]),"gold":len(all_gold_sets[a]&all_gold_sets[b])}
    save(HERE/"candidate-audit.json",ret);save(HERE/"candidate-flags.json.gz",per);print(ret,flush=True)
if __name__=="__main__":main()
