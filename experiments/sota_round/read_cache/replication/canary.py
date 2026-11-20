from io import StringIO
import json
from replay import ARMS,numbered,path_in,simulate

assert path_in("a.py","./swebench_9_15/testbed")==path_in("./swebench_9_15/testbed/a.py","./swebench_9_15")
rows=[]
sid="syn"
def add(role,m,extras=None,parent=None):
    u=str(len(rows)+1)
    p=str(len(rows)) if rows else None
    rows.append({"type":role,"cwd":"/demo","sessionId":sid,"uuid":u,"parentUuid":p if parent is None else parent,
        "message":m,"toolUseResult":extras})
def decl(mid,name,inp,tid):
    add("assistant",{"id":mid,"content":[{"type":"tool_use","name":name,"input":inp,"id":tid}]})
def result(tid,text,extra=None):
    add("user",{"content":[{"type":"tool_result","tool_use_id":tid,"content":text}]},extra)
def read(tid,raw):
    text=numbered(raw,"\u2192")+"\n\n<system-reminder>seen literal</system-reminder>\n"
    n=len(raw.split("\n"));result(tid,text,{"type":"text","file":{"content":raw,"totalLines":n,"startLine":1,"numLines":n}})
p={"file_path":"a.py"}
decl("1","Read",p,"a");decl("1","Read",p,"b");read("a","x\ny");read("b","x\ny")
decl("2","Write",{"file_path":"other.py","content":"q"},"w");result("w","File written.")
decl("3","Read",p,"c");read("c","x\ny")
decl("4","Edit",{"file_path":"a.py","old_string":"y","new_string":"Z"},"e");result("e","File updated.")
decl("5","Read",p,"d");read("d","x\nZ")
decl("6","Bash",{"command":"anything"},"b1");result("b1","ok")
decl("7","Read",p,"r7");read("r7","abc")
add("user",{"content":"branch reset"},parent="another-branch")
decl("8","Read",p,"r8");read("r8","abc")
buf=StringIO()
stats=simulate("\n".join(map(json.dumps,rows)).encode(),"s",buf,StringIO())
qs=list(map(json.loads,buf.getvalue().splitlines()))
def pick(i,name):
    return qs[i]["arms"][ARMS.index(name)]
assert not any(qs[0]["arms"]) and not any(qs[1]["arms"])
assert pick(2,"selective")[2]=="correct" and pick(2,"flush") is None
assert pick(3,"write_through")[2:4]==["correct",[3]] and pick(3,"selective") is None
assert pick(4,"write_through") is None and not any(qs[5]["arms"])
assert stats["counts"]["branch_resets"]==1
print("Passed simultaneous Read, cwd alias, sibling Write, confirmed Edit, carried literal suffix, Bash clear, and branch reset.")
