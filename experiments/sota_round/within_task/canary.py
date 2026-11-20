"""Synthetic preflight; no source trajectories or historical labels opened."""
from collections import Counter
from io import StringIO
import json
from memory import signature
from replay import replay


def assistant(*commands):
    return {"role":"assistant", "extra":{"actions":[{"command":cmd, "tool_call_id":tid} for cmd,tid in commands]}}


def tool(tid, rc, output=""):
    return {"role":"tool","tool_call_id":tid,"extra":{"returncode":rc},"content":"<output>"+output+"</output>"}


f=("cat gone.py", "F")
s=("cat working.py", "S")
msg=[assistant(f,("ls preissued.js","sib")), tool("F",1,"No such file"),tool("sib",0),
     assistant(s),tool("S",0),assistant(f),tool("F",1,"No such file"),
     assistant(s),tool("S",0),assistant(f),tool("F",1,"No such file"),
     assistant(("cat nope.py","X")),assistant(),tool("X",0),
     assistant(f),tool("F",1,"No such file"),assistant(("echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT","end")),
     tool("end",0),assistant(f),tool("F",1,"No such file")]
buf=StringIO()
counts=Counter()
stats=replay(msg,"synthetic",counts,buf)
events=list(map(json.loads,buf.getvalue().splitlines()))
assert len(events)==5 and stats["pairs"]==2
assert events[0]["n_steps"]==0 and events[0]["gold"]["target"]=="working.py"
assert events[1]["n_pair"]==1 and events[1]["recurrent"] and events[1]["fp_recurrent"]
assert events[1]["hits"]["compact"][0]==7
assert events[1]["choices"]["compact"]==[[0,0,1,0]]
assert [e["branch"] for e in events[2:]]==["next_status_unknown","next_submission","no_next_decision"]
assert signature("cd /testbed && cat ./folder/file.py")==("cat","folder/file.py")
assert signature("env FOO=1 python3 -c 'print(1)'")==("python","")
assert signature("cd /testbed/src && cat file.py")==("cat","src/file.py")
assert signature("cat /tmp/ignore.py")==("cat","")
assert signature("cat <<'EOF'\nsecret.py\nEOF")==("cat","")
assert signature("rg '*.py'")==("rg","")
print("preflight passed: unissued actions, delayed writes, missing status, submissions, same-batch siblings, strict file signature")
