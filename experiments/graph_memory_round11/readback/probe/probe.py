import collections, gzip, hashlib, importlib.util, json, math, sys
from pathlib import Path
D=Path(__file__).resolve().parent
sys.path.insert(0,str(D.parent))
from replay import tokens, packet, literal, WORK, sha, decode
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
def H(s):return sha(s.encode())
def main_prepare():
    data=read(D.parent/"views.gz");wires=read(D.parent/"wires-primary.gz")
    allrows=[];exclude=collections.Counter()
    for task,r in sorted(data.items()):
        history=[];selected=[]
        wr={v["turn"]:v for v in wires[task+"|union"]}
        for v in r["views"]:
            t=v["turn"];lines=v["lines"];by=dict(lines)
            history=[h for h in history if t-h[0]<=8]
            old=[(e,vis) for e,path,vis in history if path==v["path"]]
            raw="".join(literal(n,s) for n,s in lines)
            wire=wr.get(t,{}).get("wire") or raw
            recovered,visible,refs=decode(wire,old)
            assert recovered==lines
            history.append((t,v["path"],visible))
            if not refs:continue
            pool=[n for n,s in lines if 8<=len(s.strip())<=100 and not s.lstrip().startswith(("#",'"',"'"))]
            targets=[n for n in pool if n not in visible]
            if not targets:exclude["no_target"]+=1;continue
            sid=task+"|"+str(t);target=min(targets,key=lambda n:H(sid+"/"+str(n)))
            others=sorted((n for n in pool if by[n].strip()!=by[target].strip()),key=lambda n:H(sid+"other"+str(n)))
            choices=[target];seen={by[target].strip()}
            for n in others:
                if by[n].strip() not in seen:
                    choices.append(n);seen.add(by[n].strip())
                if len(choices)==4:break
            if len(choices)<4:exclude["short_choices"]+=1;continue
            placebo=choices[1]
            choices.sort(key=lambda n:H(sid+"choice"+str(n)))
            snippets=[]
            for e,lookup in old:
                if e in refs:
                    snippet="".join(literal(n,lookup[n]) for n in sorted(lookup) if any(abs(n-c)<=2 for c in choices))
                    if snippet:snippets.append(packet(e,snippet))
            question=(f"File: {v['path']}\nEarlier visible excerpts:\n"+ "\n".join(snippets)
                 +f"\nCurrent observation:\n{{current}}\nWhat is the exact code at line {target}, ignoring outer whitespace?\n"
                 +"\n".join(f"{i+1}. {by[c].strip()}" for i,c in enumerate(choices))+"\nAnswer with its number.")
            current={"full":packet(t,raw),"link":packet(t,wire),"focus":packet(t,wire)+f"Resolved evidence:\n"+literal(target,by[target]),
                     "control":packet(t,wire)+"Resolved evidence:\n"+literal(placebo,by[placebo])}
            # Insert only into the dedicated observation placeholder; source can contain braces.
            parts=question.rsplit("\nCurrent observation:\n{current}\n",1)
            assert len(parts)==2
            inputs={m:parts[0]+"\nCurrent observation:\n"+s+"\n"+parts[1] for m,s in current.items()}
            if max(tokens(s) for s in inputs.values())>4400:exclude["long"]+=1;continue
            selected.append((H("pick|"+sid),dict(id=sid,task=task,panel=r["panel"],target=target,arms=inputs),choices.index(target)+1))
        allrows+=sorted(selected)[:2];exclude["task_cap"]+=max(0,len(selected)-2)
    chosen=sorted(allrows)[:40]
    save(D/"inputs.json",[x for _,x,_ in chosen])
    save(D/"grading-key.json",{x["id"]:y for _,x,y in chosen})
    save(D/"input-lock.json",dict(files={f:sha((D/f).read_bytes()) for f in ("PROTOCOL_RU.md","inputs.json","grading-key.json","probe.py")},eligible=len(allrows),exclusions=exclude))
def solver():
    spec=importlib.util.spec_from_file_location("local_harness",WORK/"graph_memory_round8/agent/harness.py")
    h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h);h.D=D;h.ENDPOINT="http://127.0.0.1:18949/v1/chat/completions";return h
def run():
    lock=read(D/"input-lock.json")["files"]
    for f in ("inputs.json","PROTOCOL_RU.md","probe.py"):assert sha((D/f).read_bytes())==lock[f]
    sysmsg='Read the numbered tool evidence. A marker @event line count copies consecutive source lines from the named prior observation. Use the current observation to answer. Return only JSON {"choice": INTEGER}.'
    h=solver();rows=[]
    for row in read(D/"inputs.json"):
        for arm,question in sorted(row["arms"].items(),key=lambda x:H(row["id"]+x[0])):
            k,answer=h.call(row["id"],"lookup",sysmsg,question,36);log=h.read(D/"calls"/(k+".json.gz"))
            x=h.obj(answer).get("choice")
            rows.append(dict(id=row["id"],arm=arm,choice=x if type(x)==int and 1<=x<=4 else None,key=k,usage=log["response"]["usage"]))
    save(D/"answers.json",rows)
    save(D/"answer-lock.json",{f:sha((D/f).read_bytes()) for f in ("input-lock.json","answers.json")})
def score():
    for f,h in read(D/"answer-lock.json").items():assert sha((D/f).read_bytes())==h
    assert sha((D/"grading-key.json").read_bytes())==read(D/"input-lock.json")["files"]["grading-key.json"]
    keys=read(D/"grading-key.json");rr=read(D/"answers.json")
    arms={}
    for arm in ("full","link","focus","control"):
        rows=[x for x in rr if x["arm"]==arm];arms[arm]=dict(correct=sum(x["choice"]==keys[x["id"]] for x in rows),n=len(rows),
               invalid=sum(x["choice"] is None for x in rows),input=sum(x["usage"]["prompt_tokens"] for x in rows))
    table={r["id"]:{x["arm"]:x["choice"]==keys[x["id"]] for x in rr if x["id"]==r["id"]} for r in rr}
    pairs={}
    for a,b in (("link","full"),("focus","link"),("focus","control")):
        diff=[int(x[a])-int(x[b]) for x in table.values()];pairs[a+"-"+b]=[diff.count(1),diff.count(-1)]
    save(D/"results.json",dict(arms=arms,pairs=pairs,physical=len({x["key"] for x in rr}),tasks=len({v.rsplit("|",1)[0] for v in keys})))
if __name__=="__main__":{"prepare":main_prepare,"run":run,"score":score}[sys.argv[1]]()
