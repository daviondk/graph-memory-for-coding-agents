import hashlib,json,re,sys
from pathlib import Path
D=Path(__file__).resolve().parent
P=D.parent
sys.path.insert(0,str(P))
import probe
SYS='Read the numbered tool evidence. A marker @event line count copies consecutive source lines from the named prior observation. Use the current observation to answer. Return only JSON {"choice": INTEGER}.'
def prepare():
    original=probe.read(P/"inputs.json");gold=probe.read(P/"grading-key.json")
    prompts=[];keys=[]
    for r in original:
        full=r["arms"]["link"];a,tail=full.split("\nEarlier visible excerpts:\n",1)
        archive,current=tail.split("\nCurrent observation:\n",1)
        opts=re.findall(r"^([1-4])\. (.+)$",current.rsplit("ignoring outer whitespace?\n",1)[1],flags=re.M)
        assert len(opts)==4
        choices=dict((int(k),v) for k,v in opts);correct=gold[r["id"]];t=r["target"]
        alternative=min((k for k in choices if k!=correct),key=lambda k:probe.H("r11-do|"+r["id"]+"|"+str(k)))
        changes=[]
        def sub(m):
            before=m[2].lstrip()
            changes.append(dict(old=before,new=choices[alternative]))
            return m[1]+m[2][:len(m[2])-len(before)]+choices[alternative]
        new=re.sub(r"^("+str(t)+r"\t)([^\n]*)$",sub,archive,flags=re.M)
        assert changes and all(z["old"].strip()==choices[correct] for z in changes)
        assert f"\n{t}\t" not in current.split("\nWhat is the exact code at line",1)[0]
        body=a+"\nEarlier visible excerpts:\n"
        prompts.append(dict(id=r["id"],arms={"counterfactual":body+new+"\nCurrent observation:\n"+current,
             "no_archive":body+"[not available]\nCurrent observation:\n"+current}))
        keys.append(dict(id=r["id"],correct=correct,alternate=alternative,target=t,changes=changes))
    probe.save(D/"inputs.json",prompts);probe.save(D/"scoring.json",keys)
    probe.save(D/"lock.json",{n:probe.sha((D/n).read_bytes()) for n in ("intervene.py","PROTOCOL_RU.md","scoring.json","inputs.json")})
def run():
    lock=probe.read(D/"lock.json")
    assert all(probe.sha((D/n).read_bytes())==lock[n] for n in ("inputs.json","intervene.py","PROTOCOL_RU.md"))
    h=probe.solver();h.D=D;h.ENDPOINT="http://127.0.0.1:18950/v1/chat/completions";out=[]
    for r in probe.read(D/"inputs.json"):
        for a,prompt in sorted(r["arms"].items(),key=lambda v:probe.H(r["id"]+v[0])):
            key,response=h.call(r["id"],"lookup",SYS,prompt,36)
            x=h.obj(response).get("choice")
            out.append(dict(id=r["id"],arm=a,choice=x if type(x)==int and 1<=x<=4 else None,key=key))
    probe.save(D/"answers.json",out);probe.save(D/"sealed.json",{n:probe.sha((D/n).read_bytes()) for n in ("lock.json","answers.json")})
def grade():
    assert all(probe.sha((D/n).read_bytes())==v for n,v in probe.read(D/"sealed.json").items())
    assert probe.sha((D/"scoring.json").read_bytes())==probe.read(D/"lock.json")["scoring.json"]
    native={x["id"]:x for x in probe.read(P/"answers.json") if x["arm"]=="link"}
    answers={(x["id"],x["arm"]):x["choice"] for x in probe.read(D/"answers.json")}
    rows=[]
    for x in probe.read(D/"scoring.json"):
        i=x["id"];a,b,c=native[i]["choice"],answers[i,"counterfactual"],answers[i,"no_archive"]
        rows.append(dict(id=i,before=a,after=b,no_archive=c,old=x["correct"],alternate=x["alternate"],
                   old_correct=a==x["correct"],new_correct=b==x["alternate"],switched=a!=b,
                   both_correct=a==x["correct"] and b==x["alternate"],no_old=c==x["correct"],no_alternate=c==x["alternate"]))
    probe.save(D/"rows.json",rows)
    probe.save(D/"results.json",dict(n=len(rows),sums={k:sum(r[k] for r in rows) for k in ("old_correct","new_correct","switched","both_correct","no_old","no_alternate")},
        counterfactual_vs_no_archive=[sum(x["new_correct"] and not x["no_alternate"] for x in rows),
            sum(not x["new_correct"] and x["no_alternate"] for x in rows)]))
if __name__=="__main__":{"prepare":prepare,"run":run,"grade":grade}[sys.argv[1]]()
