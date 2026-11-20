"""Post-hoc audit of the search-result ceiling and actual agent choices. Never used for model inputs."""
from collections import Counter
from pathlib import Path
import sys
import evaluate as e
import harness as h

def normalized(event):
    if event["type"]=="read":
        s=event["span"]
        return ("read",s["path"],s["center"]) if s else ("invalid read",)
    return (event["type"],event["decision"].get("search"))

def main():
    root=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else h.D
    h.D=e.D=root;ids=e.answers()
    rows=[];summary=Counter();lower=Counter();upper=Counter()
    for i in ids:
        task=root/"tasks"/i
        row={}
        hist=h.read(task/"flat.json.gz");ptr=h.read(task/"evidence.json.gz")
        gold=h.read(task/"grades_v2/control.json")["gold"]["gold_lines"]
        cfg=h.read(task/"public_input.json.gz");allowed=cfg["paths"]
        raw=hist["shared"]["history"]; windows=[]
        for x in raw:
            _,s,_=h.view(task/"base",allowed,x["path"],x["line"])
            windows.append(bool(s and not s["truncated"] and any(s["start"]<=n<=s["end"] for n in gold.get(s["path"],[]))))
        row["gold_file_accessible"]=bool(set(allowed)&set(gold))
        row["at_least_one_hit"]=bool(raw)
        row["any_initial_hit_window_contains_gold"]=any(windows)
        row["first_initial_hit_window_contains_gold"]=bool(windows and windows[0])
        row["changed_first_action"]=normalized(hist["events"][0])!=normalized(ptr["events"][0])
        row["same_final_observations"]=hist["entries"]==ptr["entries"]
        for key,v in row.items():summary[key]+=v
        per_arm={}
        for label,trace in [("history",hist),("pointer",ptr)]:
            count=Counter()
            for j,event in enumerate(trace["events"]):
                action=normalized(event);count[action[0]]+=1
                if event["type"]=="read" and event["span"] and j==0 and raw:
                    s=event["span"];x=raw[0]
                    count["first_action_exact_initial_address"]+=int((s["path"],s["center"])==(x["path"],x["line"]))
                if event["type"]=="search" and event["decision"].get("search")==trace["shared"]["query"]:
                    count["reissued_original_literal"]+=1
            (lower if label=="history" else upper).update(count);per_arm[label]=dict(count)
        rows.append({"id":i,**row,**per_arm})
    h.write(root/"mechanism_audit.json",{"tasks":len(rows),"summary":dict(summary),"history":dict(lower),"pointer":dict(upper),"rows":rows})
if __name__=="__main__":main()
