"""Serialize data as numeric fields, compare native scores against SciPy, time two native engines."""
from runs import D,inputs,ref,shape,signal,save,sha,np
from collections import defaultdict
from pathlib import Path
import os,platform,subprocess,shutil
PRIVATE=Path("D:/CodexResearch/x20-r33-incremental-native");PRIVATE.mkdir(exist_ok=True)
def emit():
    traces,coef,bias,rank=inputs();p=PRIVATE/"numeric-input.txt"
    with p.open("w",encoding="ascii",newline="\n") as f:
        def write(arr):f.write(" ".join(map(str,arr))+"\n")
        write([*coef,bias,*rank["coef"],rank["intercept"]]);write([len(traces)])
        for tr in traces:
            attrs={};edges=set();write([len(tr["steps"])])
            for s in tr["steps"]:
                for a,*v in s["up"]:attrs[a]=v
                for a in s["rm"]:del attrs[a]
                edges.difference_update(map(tuple,s["minus"]));edges.update(map(tuple,s["plus"]))
                ids,m,deg,r=ref(attrs,edges);scores=np.column_stack((shape(m),np.log1p(deg),r))@coef+bias
                where={v:j for j,v in enumerate(ids)}
                write([len(s[v]) for v in ("up","rm","minus","plus","dense")]+[len(ids)])
                for row in s["up"]:write(row)
                write(s["rm"])
                for name in ("minus","plus"):
                    for row in s[name]:write(row)
                for a,sc in zip(ids,scores):write([a,sc])
                for q in s["dense"]:
                    write([len(q)]);write(q);write(np.argsort(-(scores[[where[a] for a in q]]+signal(len(q),len(q),rank)),kind="stable"))
    return p,traces
def run():
    p,trs=emit();compiler=shutil.which("g++");assert compiler is not None
    ver=subprocess.check_output([compiler,"--version"],encoding="utf8").splitlines()[0]
    exe=PRIVATE/"native.exe";flags=["-O3","-std=c++17"]
    subprocess.run([compiler,*flags,str(D/"native.cpp"),"-o",str(exe)],check=True)
    output=PRIVATE/"native-times.txt"
    subprocess.run([str(exe),str(p),str(output)],check=True)
    lines=output.read_text().splitlines();status,ns,nq,err=lines.pop(0).split();assert status=="ok"
    times=defaultdict(lambda:defaultdict(list))
    for line in lines:
        t,f,scope,inc,rep,dt=map(int,line.split())
        times[t,f,scope][inc].append(dt/10)
    raw=[];summary={}
    groups=[("all",set(range(len(trs)))),("each_batch",{i for i,v in enumerate(trs) if v["dense_schedule"]}),("quartiles",{i for i,v in enumerate(trs) if not v["dense_schedule"]})]
    def summarize(i,fon,scope):
        group=[times[t,fon,scope] for t in sorted(i)];inc=np.array([np.median(v[1]) for v in group]);defer=np.array([np.median(v[0]) for v in group]);log=np.log(inc/defer)
        ix=np.random.default_rng(13).integers(len(log),size=(10000,len(log)));bs=np.exp(log[ix].mean(axis=1))
        return dict(traces=len(group),inc_ms=inc.sum()/1e6,defer_ms=defer.sum()/1e6,geometric_ratio=[float(np.exp(log.mean())),*np.quantile(bs,[.025,.975]).tolist()])
    assert len(times)==len(trs)*6
    for key,rec in times.items():
        assert len(rec[0])==len(rec[1])==5
        t,f,s=key;raw.append(dict(t=trs[t]["t"],frequency=f,scope=s,ns=rec))
    for group,ids in groups:
        summary[group]={}
        for f,fn in enumerate(("each","fourth","last")):
            for s,sn in enumerate(("all","eight")):summary[group][fn+"/"+sn]=summarize(ids,f,s)
    save(D/"native-times.json.gz",raw)
    save(D/"native-results.json",{"traces":len(trs),"states":int(ns),"question_states":int(nq),"max_abs_logit_error":float(err),"compiler":ver,"flags":flags,
        "numerical_input_sha":sha(p),"fixture_plan":sha(D/"fixture-lock.json"),"native_source":sha(D/"native.cpp"),"wrapper":sha(D/"native_run.py"),
        "exe_sha":sha(exe),"timing_sha":sha(D/"native-times.json.gz"),"os":platform.platform(),"cpu":os.environ.get("PROCESSOR_IDENTIFIER"),"protocol":sha(D/"NATIVE_PROTOCOL_RU.md"),"summary":summary})
if __name__=="__main__":run()