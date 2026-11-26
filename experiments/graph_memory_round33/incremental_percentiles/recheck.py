"""Independent second replay of the same binary. The first measurement remains primary."""
from native_run import PRIVATE,D,sha,save,np,subprocess
from runs import load
from collections import defaultdict
old=load(D/"native-results.json");exe=PRIVATE/"native.exe";src=PRIVATE/"numeric-input.txt"
assert sha(exe)==old["exe_sha"] and sha(src)==old["numerical_input_sha"]
out=PRIVATE/"native-repeat.txt";subprocess.run([str(exe),str(src),str(out)],check=True)
lines=out.read_text().splitlines();status=lines.pop(0);times=defaultdict(lambda:defaultdict(list))
for l in lines:
    t,f,s,a,r,dt=map(int,l.split());times[t,f,s][a].append(dt/10)
raw=[dict(t=t,f=f,s=s,ns=v) for (t,f,s),v in sorted(times.items())]
save(D/"native-repeat-times.json.gz",raw)
res={}
for f,fn in enumerate(("each","fourth","last")):
    for s,sn in enumerate(("all","eight")):
        v=[times[t,f,s] for t in range(48)];logs=np.log([np.median(p[1])/np.median(p[0]) for p in v])
        ix=np.random.default_rng(13).integers(48,size=(10000,48))
        res[fn+"/"+sn]=[float(np.exp(logs.mean())),*np.exp(np.quantile(logs[ix].mean(axis=1),[.025,.975])).tolist()]
save(D/"native-repeat.json",{"summary":res,"independent_replay_status":status,"source":sha(D/"native-results.json"),"timing":sha(D/"native-repeat-times.json.gz"),"code":sha(D/"recheck.py")})