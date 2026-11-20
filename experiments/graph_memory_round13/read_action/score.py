"""Evaluate sealed reads; truth is opened only after actual actions and receipts are written."""
import collections
import itertools
import json
from experiment import ROOT, PANELS, ARMS, load, save, sha

def main():
    for name,digest in load(ROOT/"read-lock.json").items():
        assert sha((ROOT/name).read_bytes())==digest
    cases={r["id"]:r for r in load(ROOT/"cases.gz")}
    reads={(a["id"],a["arm"]):a for a in load(ROOT/"reads.gz")}
    actions={(r["id"],r["method"]):r for r in [json.loads(l) for l in (ROOT/"model.jsonl").read_bytes().splitlines()]}
    assert set(reads)==set(actions) and len(actions)==3*len(cases)
    labels={}
    for panel,d in PANELS.items():
        labels[panel]=({r["iid"]:r for r in load(d/"patch_labels.json.gz")},
                       {r["id"]:r["target"] for r in load(d/"navigation_labels.json.gz")})
    results={}
    all_rows=[]
    for panel in PANELS:
        patches,nav=labels[panel]
        panel_rows=[]
        for c in cases.values():
            if c["panel"]!=panel:continue
            ref=patches[c["iid"]];strict=bool(ref.get("strict",False) and ref.get("prod"))
            group={}
            for arm in ARMS:
                pair=c["id"],arm
                read=reads[pair];a=actions[pair]
                chosen=read["path"] if read["opened"] else None
                group[arm]=dict(chosen=chosen, valid=a["valid"], opened=read["opened"],cue=c["candidates"][arm],
                              selected_cue=chosen==c["candidates"][arm] if arm!="none" and chosen else False,
                              patch=bool(chosen in ref["prod"]) if strict else None,
                              nav=bool(chosen==nav[c["id"]]["path"]) if nav[c["id"]] else None,
                              in_tokens=a["usage"]["prompt_tokens"],out_tokens=a["usage"]["completion_tokens"])
            panel_rows.append(dict(id=c["id"],iid=c["iid"],panel=panel,strict_patch=strict,roles=group))
        summary={}
        for arm in ARMS:
            rows=[r["roles"][arm] for r in panel_rows]
            counts={k:sum(r[k] for r in rows if r[k] is not None) for k in
                        ["valid","opened","selected_cue","patch","nav","in_tokens","out_tokens"]}
            for k in ["patch","nav"]:
                counts[k+"_n"]=sum(r[k] is not None for r in rows)
            summary[arm]=counts
        pairs={}
        for a,b in itertools.combinations(ARMS,2):
            diffs=[(r["roles"][a],r["roles"][b]) for r in panel_rows]
            p=[(a["patch"],b["patch"]) for a,b in diffs if a["patch"] is not None]
            pairs[a+"->"+b]=dict(changed_choice=sum(l["chosen"]!=r["chosen"] for l,r in diffs),n=len(diffs),
                                  gains=sum(not x and y for x,y in p),losses=sum(x and not y for x,y in p),
                                  tied=sum(x==y for x,y in p),patch_n=len(p))
        results[panel]=dict(n_tasks=len(panel_rows),arms=summary,paired=pairs)
        all_rows.extend(panel_rows)
    save(ROOT/"outcomes.gz",all_rows)
    save(ROOT/"results.json",results)
    print(json.dumps(results))
if __name__=="__main__":main()
