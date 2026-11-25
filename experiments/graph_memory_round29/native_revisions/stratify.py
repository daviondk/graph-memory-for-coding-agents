"""Post-hoc diagnostics for different behavior of two fixed readers after the same edits."""
from pathlib import Path
from collections import defaultdict
from statistics import mean
import gzip,json
from fetch import ROOT,save
from prepare import views,normalize,metrics
def load(p):return json.loads(gzip.decompress(p.read_bytes()))
def main():
    cases=load(ROOT/"outcomes.json.gz");local=load(ROOT.parent/"revision_reader/forecasts.json.gz")
    old,new=views("original"),views("edits");groups=defaultdict(list)
    for q,r in cases.items():
        old_texts,og=old[q];new_texts,ng=new[q]
        overlap=bool({normalize(t) for t in og}&{normalize(t) for t in ng})
        change=tuple(i for i,(a,b) in enumerate(zip(old_texts,new_texts)) if a!=b)
        label={(): "unchanged",(0,):"background",(1,):"situation",(2,):"question"}.get(change,"multiple")
        local_delta=100*(metrics(local[q]["new"]["text"],ng)[0]-metrics(local[q]["old"]["text"],ng)[0])
        official_delta=100*(r["cold"][0]-r["old"][0]);vec=(official_delta,local_delta)
        groups["new_gold_overlaps_old" if overlap else "no_gold_overlap"].append(vec)
        groups["changed_"+label].append(vec)
    result={}
    for flag,values in sorted(groups.items()):
        result[flag]={"n":len(values),"refresh_minus_old_F1_pp":{"native":mean(v[0] for v in values),"local":mean(v[1] for v in values)}}
    save("strata.json",result)
if __name__=="__main__":main()
