"""Lock actual choices of the candidate and archive query before opening any new tests."""
import ast
from concurrent.futures import ThreadPoolExecutor
import itertools,re
from base import D,read,save,sha,stable,execute
from pred_process import run_predictions
from policy import POLICIES
from safe_ast import checked

def program(raw,source,entry):
    msg=raw.strip()
    blocks=re.findall(r"```(?:python|py)?\s*\n(.*?)```",msg,re.S|re.I)
    if blocks:msg=blocks[0].strip()
    try:
        tree=checked(msg)
        names=[n.name for n in tree.body if isinstance(n,ast.FunctionDef)]
        if names.count(entry)!=1 or any(not isinstance(n,(ast.FunctionDef,ast.Import,ast.ImportFrom,ast.Assign,ast.AnnAssign)) for n in tree.body):
            raise ValueError("not a module containing the required single target")
        prefix=[n for n in ast.parse(source).body if isinstance(n,(ast.Import,ast.ImportFrom))]
        imports={ast.unparse(n) for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom))}
        tree.body=[n for n in prefix if ast.unparse(n) not in imports]+tree.body
        return ast.unparse(tree),""
    except (SyntaxError,ValueError,TypeError) as e:return "",type(e).__name__+": "+str(e)[:110]
def callargs(cards,entry):
    out=[]
    for stmt in cards:
        nodes=[n for n in ast.walk(ast.parse(stmt)) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id==entry]
        assert len(nodes)==1;out.append([ast.literal_eval(a) for a in nodes[0].args])
    return out
def rec(task,key,folder):
    receipt=read(folder+"/"+key+".json.gz")
    assert sha(stable(receipt["request"]))==key
    code,why=program(receipt["reply"]["choices"][0]["message"].get("content") or "",task["source"],task["name"])
    return dict(key=key,source=code,why=why,finish=receipt["reply"]["choices"][0]["finish_reason"],usage=receipt["reply"]["usage"])
def evidence(task,prog):
    h=task["cards"];n=len(h)
    if not prog["source"]:return [0]*n,["invalid"]*n,{"invalid":prog["why"]}
    actual=execute(dict(source=prog["source"],name=task["name"],examples=h))
    tags=run_predictions(dict(source=prog["source"],name=task["name"],args=callargs(h,task["name"])))
    return actual.get("bits",[0]*n),tags.get("labels",["process"]*n),{"assertions":actual,"outcomes":tags.get("status")}
def picks(history,passed):
    vals=[sum(vec[i] for i in history) for vec in passed]
    return [j for j,v in enumerate(vals) if v==max(vals)]
def probe(mode,indices,leaders,tags,available):
    unseen=[i for i in range(len(available)) if i not in indices]
    if not unseen:return None
    if mode=="recent":return unseen[-1]
    if mode=="failed":return max(unseen,key=lambda i:(available[i][2]&1,i))
    def pairs(i,bank):
        return sum(tags[a][i]!=tags[b][i] for a,b in itertools.combinations(bank,2))
    return max(unseen,key=lambda i:(pairs(i,leaders),pairs(i,range(len(tags))),i))
def main():
    for name in ("predictions_lock.json","sample_decisions.json","writer_lock.json"):
        assert all(sha((D/n).read_bytes())==h for n,h in read(name).items())
    packet={r["id"]:r for r in read("packets.json.gz")};assign=read("assign.json");sample=read("sample_assignment.json")
    tasks=read("past.json.gz");decisions=[];logs=[]
    with ThreadPoolExecutor(6) as pool:
        for t in tasks:
            i=t["id"];candidates=[rec(t,assign[i]["empty"],"calls")]+[rec(t,k,"sample_calls") for k in sample[i]]
            a=list(pool.map(lambda p:evidence(t,p),candidates))
            passed=[z[0] for z in a];tags=[z[1] for z in a]
            m=packet[i]["memory"];all_history=m["all"];plans={}
            for arm in POLICIES:
                indices=[x[0] for x in m[arm]]
                leaders=picks(indices,passed)
                plans[arm]=dict(chosen=leaders[0],cards=indices,leaders=leaders,probe=None)
            initial=plans["union"]
            for mode in ("recent","failed","split"):
                chosen=probe(mode,initial["cards"],initial["leaders"],tags,all_history)
                indices=initial["cards"]+([chosen] if chosen is not None else [])
                leaders=picks(indices,passed)
                plans["read_"+mode]=dict(chosen=leaders[0],cards=indices,leaders=leaders,probe=chosen)
            decisions.append(dict(id=i,candidates=candidates,plans=plans));logs.append(dict(id=i,witnesses=passed,fingerprints=tags,runs=[x[2] for x in a]))
    save("selected_candidates.json.gz",decisions);save("selection_observations.json.gz",logs)
    save("choices_lock.json",{n:sha((D/n).read_bytes()) for n in ["decide.py","pred_runner.py","pred_process.py","predictions_lock.json","sample_decisions.json","selected_candidates.json.gz","selection_observations.json.gz"]})
if __name__=="__main__":main()

