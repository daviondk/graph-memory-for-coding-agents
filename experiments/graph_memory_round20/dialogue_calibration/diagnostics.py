"""Descriptive sensitivity to score ties and sum of stored whitespace words at the fixed 20% turn budget."""
import json
import math
import numpy as np
import run as exp

def main():
    raw=json.loads(exp.tr.TARGET.read_bytes())
    native={exp.tr.digest(q["question_id"]):[(len(x["content"].split()),int(x.get("has_answer") is True))
                 for ss in q["haystack_sessions"] for x in ss] for q in raw}
    del raw
    split=exp.load("split.json")["folds"]
    vals={"strict":{},"all":{}}
    for i,fold in enumerate(split):
        for rec in exp.load(f"pred-{i:02d}.json.gz"):
            a=np.asarray(native[rec["id"]])
            words=a[:,0]
            y=a[:,1]
            k=math.ceil(.2*len(y))
            for arm in list(exp.ARM)+["uniform","user_first"]:
                scores=np.array(rec["score"][arm]) if arm in exp.ARM else (np.array(rec["user"]) if arm=="user_first" else np.zeros(len(y)))
                order=np.argsort(-scores)
                cut=scores[order[k-1]]
                above=scores>cut
                tied=scores==cut
                weight=(k-above.sum())/tied.sum()
                expected_hits=y[above].sum()+weight*y[tied].sum()
                selected_words=words[above].sum()+weight*words[tied].sum()
                actual=words[order[:k]].sum() if arm in exp.ARM else selected_words
                for s in (["strict","all"] if fold["section"]=="strict" else ["all"]):
                    o=vals[s].setdefault(arm,{"tied":0,"word":[],"eR":[]})
                    o["tied"]+=int(k<len(y) and scores[order[k]]==cut)
                    o["word"].append(actual/words.sum())
                    if y.sum()>0:
                        o["eR"].append(expected_hits/y.sum())
    for s in vals:
        for a in vals[s]:
            o=vals[s][a]
            o["word"]=float(np.mean(o["word"]))
            o["eR"]=float(np.mean(o["eR"]))
    exp.save("tie-and-words.json",vals)
    print(vals)
if __name__=="__main__":
    main()
