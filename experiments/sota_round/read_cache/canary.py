from io import StringIO
import json
from run import ARMS,observation,simulate
from shell import classify

q="cd /repo && cat x.py"
assert classify(q).paths==("/repo/x.py",)
assert classify("cd /repo && sed -n '1,20p' src/x.py | head -5").mode=="query"
assert classify("rg -n 'tiny pattern' /repo/x.py").mode=="query"
assert classify("cat x.py").mode=="readonly"
assert classify("cat /dev/random").mode=="readonly"
assert classify("cd /repo && sed -n '1p' -e 'e touch z.py' x.py").mode=="global"
assert classify("python -c 'do()'").mode=="global"
assert classify("cd /repo && cat >y.py <<'END'\nthis is data\nEND").paths==("/repo/y.py",)
assert classify("cd /repo && rm x.py").paths==("/repo/x.py",)
assert classify("cd /repo").mode=="global"
assert classify("cat /repo/a.py; touch /repo/b.py").mode=="global"
def message(tid,out,rc=0):
    return {"role":"tool","tool_call_id":tid,"extra":{"returncode":rc,"raw_output":out},
            "content":f"<returncode>{rc}</returncode>\n<output>\n{out}</output>"}
trunc=message("t","untruncated text")
trunc["content"]="<warning>clipped</warning><output_head>u</output_head>"
obs=observation(trunc)
assert obs.body==b"untruncated text" and not obs.writable and obs.clipped
logs=[]
def emit(*pairs):
    actions=[{"tool_call_id":str(i),"command":cmd} for i,(cmd,_) in enumerate(pairs)]
    logs.append({"role":"assistant","extra":{"actions":actions}})
    logs.extend(message(str(i),out) for i,(_,out) in enumerate(pairs))
emit((q,"one\n")); emit(("cd /repo && touch other.py",""));emit((q,"one\n"))
emit(("cd /repo && rm x.py","")); emit((q,"two\n"));emit((q,"two\n"))
emit((q,"two\n"),("python mutate.py",""));emit((q,"three\n"))
qbuf=StringIO();simulate(logs,"canary",qbuf,StringIO())
rows=[json.loads(s) for s in qbuf.getvalue().splitlines()]
def got(row,name):
    entry=rows[row]["arms"][ARMS.index(name)]
    return None if entry is None else (entry[0],entry[2])
assert len(rows)==5 and got(1,"selective")==(0,"correct") and got(1,"flush") is None
assert got(2,"selective") is None and got(2,"lru")==(0,"stale")
assert got(3,"lru")==(0,"stale") and got(3,"selective")==(4,"correct")
assert got(4,"selective") is None and got(1,"ttl1") is None
print("Verified classifications, combined output, freshness after a hit, local/global changes and mixed batches.")
