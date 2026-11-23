"""Read only public command receipts; never execute a command from the archive."""
from collections import Counter,defaultdict
import gzip
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from statistics import mean

HERE=Path(__file__).resolve().parent
WORK=HERE.parents[1]
sys.path.insert(0,str(WORK/"graph_memory_round16/pytest_action"))
spec=importlib.util.spec_from_file_location("historical_prepare",WORK/"graph_memory_round16/pytest_action/prepare.py")
legacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(legacy)
old=legacy.old
sys.path.insert(0,str(WORK/"graph_memory_round19/write_learned"))
from forecast_write import choose,stream
BASE=WORK/"graph_memory_round19/write_learned"
PRIV=Path("D:/CodexResearch/x20-r20-code-transfer-private/vibe")
REPOS="mpmath/mpmath pybamm-team/PyBaMM fatiando/harmonica bashtage/arch pyqtgraph/pyqtgraph xgcm/xgcm codezonediitj/pydatastructs brazilian-utils/brutils-python".split()
READ_CMD=re.compile(r"^(?:cat|head|tail|sed\s+-n|rg|grep|ls|pwd|git\s+(?:diff|show|status|log))\b")
EDIT=re.compile(r"(?:\b(?:apply_patch|git\s+(?:apply|checkout|restore|reset|commit)|sed\s+-i|patch)\b|\b(?:write_text|write_bytes)\s*\(|(?<![0-9])>{1,2}\s*[^&])")
ROOTED=re.compile(r"^\s*cd\s+(/[a-zA-Z0-9_./-]+)\s*&&")
ANSI=re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def h(s):
    if isinstance(s,Path):s=s.read_bytes()
    if isinstance(s,str):s=s.encode()
    return hashlib.sha256(s).hexdigest()


def put(p,x):
    data=(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode()
    p.write_bytes(gzip.compress(data,mtime=0) if p.suffix==".gz" else data)


def get(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)


def selector(cmd,repo):
    if legacy.BAD.search(cmd.replace("_"," ")) or old.BAD.search(cmd):return None
    kind=old.parse(cmd)
    if not kind or not kind["direct"]:return None
    key=legacy.selector(kind,repo)
    return key if key and "::" not in key else None


def content(reply):
    m=old.WRAP.fullmatch(reply.get("content",""))
    rc=reply.get("extra",{}).get("returncode")
    if not m or type(rc)!=int or int(m[1])!=rc:return "",None
    return ANSI.sub("",m[2]).strip("\r\n"),rc


def failures(text,path):
    f=re.escape(path)
    # Optional test class. Bound parameterised identifiers by their true delimiter.
    node=f+r"(?:::[A-Za-z_][A-Za-z0-9_]*){1,3}(?:\[[^\]\r\n]{1,180}\])?"
    summary=re.findall(r"(?m)^FAILED\s+("+node+r")(?=\s+-\s+|\r?$)",text)
    verbose=re.findall(r"(?m)(?<![\w/])("+node+r")\s+FAILED(?:\s|$)",text)
    return sorted(set(summary+verbose))


def keep_issue(msgs):
    user=next((m.get("content","") for m in msgs if m.get("role")=="user"),"")
    issue=user.partition("</pr_description>")[0]
    return not old.BAD.search(issue) and not legacy.BAD.search(issue)


def design():
    PRIV.mkdir(parents=True,exist_ok=True)
    archive=old.upstream.V
    src=get(archive/"memory-stage-fetch/source-manifest.json")
    assert src["sha"]=="11164976b4f920cdb0d0cd570ca572e49acea1e8"
    available={v["rfilename"]:v for v in src["siblings"]}
    roster=get(WORK/"graph_memory_round17/receipt_invalidation/paired-evidence.gz")
    old_issues={(r["repo"],str(r["iid"])) for r in roster}
    hist=old.upstream.H
    universe=[];summary={};sources={}
    for repo in REPOS:
        counts=Counter();eligible=[]
        for f in sorted((hist/repo.replace("/","__")).glob("*/*.traj.json")):
            iid=str(f.parent.name);counts["files"]+=1
            if (repo,iid) in old_issues:counts["previous_panel"]+=1;continue
            raw=f.read_bytes();msgs=json.loads(raw)["messages"]
            ad=f.relative_to(archive/"benchmark").as_posix();integrity=available[ad]
            release=integrity.get("lfs",{}).get("sha256") or integrity["blobId"]
            actual=h(raw) if len(release)==64 else hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
            assert actual==release
            if not keep_issue(msgs):counts["issue_excluded"]+=1;continue
            counts["screened"]+=1;seen={};candidates=[]
            for step,cmd,_ in old.upstream.pairs(msgs):
                file=selector(cmd,repo)
                if not file:continue
                key=(file,cmd.strip())
                counts["eligible_commands"]+=1
                if key in seen:
                    counts["pairs"]+=1;first=seen[key]
                    code=h("|".join(["R20 archive",repo,iid,str(first),str(step)]))
                    candidates.append(dict(id=code,repo=repo,iid=iid,previous=first,next=step,path=file,
                        command_sha=h(cmd.strip()),source=ad,source_sha=h(raw)))
                seen[key]=step
            if candidates:eligible.append(min(candidates,key=lambda x:x["id"]))
        counts["eligible_issues"]=len(eligible)
        selected=sorted(eligible,key=lambda x:x["id"])[:12];universe.extend(selected)
        counts["after_repo_cap"]=len(selected);summary[repo]=dict(counts)
    chosen=sorted(universe,key=lambda x:x["id"])[:64]
    lock=dict(protocol=h(HERE/"PROTOCOL_RU.md"),script=h(HERE/"study.py"),upstream=src["sha"],branches=summary,
        roster=chosen,model=h(BASE/"model.json"),tokenizer=h(stream.TOKENIZER))
    assert lock["model"]=="403fef4a84746cdf3fa1c6c73ddc96d55432ff01f93be9a87a28ac67b5200513"
    put(HERE/"design-lock.json",lock)
    print("eligible by repo",[(k,v.get("eligible_issues",0)) for k,v in summary.items()],"selected",len(chosen))


def prepare():
    plan=get(HERE/"design-lock.json")
    assert plan["script"]==h(HERE/"study.py")
    cards={};truth={}
    for row in plan["roster"]:
        f=old.upstream.V/"benchmark"/row["source"];assert h(f)==row["source_sha"]
        msgs=json.loads(f.read_bytes())["messages"];events=[];last=None;edit=False;unknown=0
        for step,cmd,reply in old.upstream.pairs(msgs):
            if step>row["next"]:break
            if step==row["next"]:
                assert h(cmd.strip())==row["command_sha"]
                text,rc=content(reply)
                truth[row["id"]]=dict(text=text,rc=rc);break
            if step>row["previous"] and EDIT.search(cmd):edit=True
            acceptable=not legacy.BAD.search(cmd.replace("_"," ")) and not old.BAD.search(cmd)
            file=selector(cmd,row["repo"]) if acceptable else None
            stripped=ROOTED.sub("",cmd).strip()
            read=acceptable and READ_CMD.search(stripped) and not re.search(r"(?:\n|&&|[;|><])",stripped)
            if not read and not file:
                if step>row["previous"]:unknown+=1
                continue
            txt,rc=content(reply)
            if rc is None:continue
            events.append([step,cmd,txt,file])
            if file==row["path"]:last=txt
        cards[row["id"]]=dict(events=events,last=last,edit=edit,unknown_steps=unknown)
    put(PRIV/"cards.json.gz",cards);put(PRIV/"outcomes.json.gz",truth)
    put(HERE/"input-lock.json",dict(sources=h(PRIV/"cards.json.gz"),labels=h(PRIV/"outcomes.json.gz"),design=h(HERE/"design-lock.json")))


def snippets(ids,blocks,ad,fields):
    spans=[]
    for j in sorted(ids):
        e,a,b,*_=blocks[j]
        if spans and spans[-1][0]==e and spans[-1][2]==a:spans[-1][2]=b
        else:spans.append([e,a,b])
    return [fields[ad[e][0]][a:b] for e,a,b in spans]


def predict():
    plan=get(HERE/"design-lock.json");lock=get(HERE/"input-lock.json")
    assert h(PRIV/"cards.json.gz")==lock["sources"] and h(HERE/"study.py")==plan["script"]
    cards=get(PRIV/"cards.json.gz");model=get(BASE/"model.json")
    tok=stream.Tokenizer.from_file(str(stream.TOKENIZER));tok.no_truncation();tok.no_padding()
    forecasts=[]
    for case in plan["roster"]:
        key=case["id"];card=cards[key];fields={};p=[]
        for step,cmd,txt,_ in card["events"]:
            for output,st in enumerate([cmd,txt]):
                eid=f"e{step:05d}-{output}";fields[eid]=st
                p.append(dict(metadata=dict(message_index=step,sub_index=output,tool_name="exec",node_kind="content.tool_output" if output else "argument"),
                    source_spans=[dict(event_id=eid,json_pointer="/content" if output else "/arguments")]))
        assert p
        ad,blocks,keys,unmatched=stream.stream_blocks(fields,p,tok);assert not unmatched
        cost=[b[3] for b in blocks]
        f=choose(ad,blocks,fields,p,model)
        kept={a:f["tokens/"+a][0] for a in ("full","positional")}
        kept.update({a:stream.select(cost,keys,stream.POLICIES.index(a),8192) for a in ("fifo","output_head")})
        kept["full_history"]=list(range(len(cost)))
        question=stream.content_tokens("Which previously failed pytest test in "+case["path"]+" will fail on rerun? Exact failed test nodeid.")
        lex=[stream.content_tokens(fields[ad[e][0]][a:b]) for e,a,b,_,_ in blocks];arms={}
        for arm,keep in kept.items():
            sel=stream.read(keep,cost,lex,[("q",question)])["q"]
            nodes={n for s in snippets(sel,blocks,ad,fields) for n in failures(s,case["path"])}
            arms[arm]=dict(choice=h(min(nodes)) if nodes else None,stored=sum(cost[j] for j in keep),read=sum(cost[j] for j in sel))
        ns=failures(card["last"] or "",case["path"]);node=min(ns,default=None)
        arms["last_receipt"]=dict(choice=h(node) if node else None,bytes=1+(len(node.encode()) if node else 0))
        forecasts.append(dict(id=key,repo=case["repo"],arms=arms,raw_tokens=sum(cost),events=len(p),
            edits=card["edit"],unknown_steps=card["unknown_steps"],old_observed=card["last"] is not None))
    put(HERE/"forecast.json",forecasts)
    put(HERE/"forecast-seal.json",dict(sha=h(HERE/"forecast.json"),input=h(HERE/"input-lock.json")))


def score():
    forecasts=get(HERE/"forecast.json");seal=get(HERE/"forecast-seal.json");src=get(HERE/"input-lock.json")
    assert seal["sha"]==h(HERE/"forecast.json") and src["labels"]==h(PRIV/"outcomes.json.gz")
    roll=get(PRIV/"outcomes.json.gz");cases={r["id"]:r for r in get(HERE/"design-lock.json")["roster"]}
    results=[]
    for f in forecasts:
        q=f["id"];case=cases[q];target=roll[q];txt=target["text"];rc=target["rc"]
        st,_=legacy.terminal(txt);nodes={h(n) for n in failures(txt,case["path"])}
        ok=(st=="pass" and rc==0 and not nodes)
        fail=st=="fail" and rc==1 and bool(nodes)
        if re.search(r"(?im)^ERROR\s+\S+|Interrupted:|INTERNALERROR>|\b\d+ errors?\b",txt.splitlines()[-1] if txt.splitlines() else ""):
            ok=fail=False
        label="clean" if ok else "failed" if fail else "unknown"
        scores={a:bool((ok and v["choice"] is None) or (fail and v["choice"] in nodes)) for a,v in f["arms"].items()}
        results.append(dict(id=q,label=label,repo=case["repo"],actual=sorted(nodes),rc=rc,scores=scores))
    put(HERE/"outcomes.json",results)
    by={};summary=Counter(r["label"] for r in results)
    for arm in ["full","output_head","fifo","positional","full_history","last_receipt"]:
        by[arm]=dict(total=sum(r["scores"][arm] for r in results),positive=sum(r["scores"][arm] for r in results if r["label"]=="failed"),
            negative=sum(r["scores"][arm] for r in results if r["label"]=="clean"),choose=sum(f["arms"][arm]["choice"] is not None for f in forecasts),
            wins=sum(r["scores"]["full"] and not r["scores"][arm] for r in results),losses=sum(r["scores"][arm] and not r["scores"]["full"] for r in results))
    obj=dict(counts=summary,by=by,n=len(results),overflow=sum(r["raw_tokens"]>8192 for r in forecasts),
            old_observed=sum(r["old_observed"] for r in forecasts),edit_observed=sum(r["edits"] for r in forecasts),
            unknown_steps=sum(r["unknown_steps"]>0 for r in forecasts),
            index_max_bytes=max((r["arms"]["last_receipt"]["bytes"] for r in forecasts),default=0))
    put(HERE/"results.json",obj);print(obj)

if __name__=="__main__":globals()[sys.argv[1]]()
