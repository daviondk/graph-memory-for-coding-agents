"""Post-primary conditional control using the archived counts of exact winning addresses."""
from study import *

def run(records):
    out={}
    for panel,panelrows in records.items():
        rows=[]
        for q,r in sorted(panelrows.items()):
            base=int(np.argmax(r["raw"]));status=r["winner"]!=base
            choices={int(i):n for i,n in r["pair"]["win"].items() if (int(i)!=base)==status}
            assert choices and r["winner"] in choices
            smoke=dict(win=choices,n=sum(choices.values()),success=sum(n*r["good"][i] for i,n in choices.items()))
            rows.append(dict(correct=r["correct"],pair=smoke,triple=smoke,unrestricted=smoke,switch=status))
        answer=summaries(rows)["pair"]
        out[panel]=dict(switches=sum(r["switch"] for r in rows),n=len(rows),**answer)
    return out
if __name__=="__main__":
    s=run(rd(D/"records.json.gz"));save("switch.json",dict(panels=s,protocol=sha(D/"SWITCH_PROTOCOL_RU.md"),records=sha(D/"records.json.gz")))
    print(json.dumps(s))

