import ast, gzip, hashlib, json, pathlib, re, sys
HERE=pathlib.Path(__file__).resolve().parent
OLD=HERE.parents[1]/"memory_session6/repair"
def sha(s):
    return hashlib.sha256(s.encode() if isinstance(s,str) else s).hexdigest()
def save(p,v):
    p.write_text(json.dumps(v,ensure_ascii=True,sort_keys=True,indent=2),encoding="utf8")
def read(p):
    return json.loads(p.read_bytes())
def signature(code):
    try:
        fs=[n for n in ast.parse(code).body if isinstance(n,ast.FunctionDef)]
    except SyntaxError:
        return None
    if len(fs)!=1:return None
    f=fs[0];a=f.args
    if a.posonlyargs or a.kwonlyargs or a.vararg or a.kwarg or a.defaults or any(p.annotation for p in a.args) or f.returns:return None
    return f.name+"("+", ".join(x.arg for x in a.args)+")"
def corpus():
    roster=read(OLD/"roster.json")
    excluded=set(map(int,roster["exclusions"]))
    prev={r["id"]:r for r in roster["items"]}
    # Only publisher interface names are exported from the reference side.
    plus_interfaces={}
    for line in gzip.decompress((OLD/"mbppplus.jsonl.gz").read_bytes()).splitlines():
        row=json.loads(line)
        try: names={n.name for n in ast.parse(row["code"]).body if isinstance(n,ast.FunctionDef)}
        except SyntaxError: continue
        plus_interfaces[int(row["task_id"])]=names
    rejected=re.compile(r"password|encrypt|decrypt|cipher|malware|weapon|missile|vulnera|attack|exploit|bacteri|medical|viral|pathogen",re.I)
    known=[];new=[]
    for r in read(OLD/"upstream-sanitized-mbpp.json"):
        i=r["task_id"]; sig=signature(r["code"])
        if i in excluded or not 11<=i<=510 or not sig or rejected.search(r["prompt"]+" "+sig) or sig.split("(")[0] not in plus_interfaces.get(i,{}):continue
        if not r["test_list"]:continue
        item=dict(id=i,spec=r["prompt"],sig=sig,entry=sig.split("(")[0],public_assert=r["test_list"][0],
                  public_args=[],imports=r.get("test_imports",[]))
        for test in r["test_list"]:
            try: calls=[f for f in ast.walk(ast.parse(test)) if isinstance(f,ast.Call) and isinstance(f.func,ast.Name) and f.func.id==item["entry"] and not f.keywords]
            except SyntaxError:continue
            for call in calls:
                try:args=tuple(ast.literal_eval(a) for a in call.args)
                except (ValueError,TypeError,SyntaxError):continue
                if len(repr(args))<=600 and repr(args) not in item["public_args"]:
                    item["public_args"].append(repr(args))
        if i in prev:known.append(item)
        else:new.append(item)
    new=sorted(new,key=lambda r:sha("r2new|"+str(r["id"])))[:48]
    for cohort, items in [("old",known),("fresh",new)]:
        for it in items:it["panel"]=cohort
    assert not ({x["id"] for x in known}&{x["id"] for x in new}) and len(new)==48
    return known+new
def main():
    its=corpus();save(HERE/"inputs.json",its)
    for it in its:
        i=it["id"];dest=HERE/"programs"/str(i);dest.mkdir(exist_ok=True,parents=True)
        if it["panel"]=="old":
            for j,branch in enumerate(("current","raw","note")):
                key=read(OLD/"tasks"/str(i)/(branch+".json"))["call"]
                best=OLD/"cap1024/programs"/(key+".py")
                source=best if best.exists() else OLD/"tasks"/str(i)/(branch+".py")
                (dest/(str(j)+".py")).write_bytes(source.read_bytes())
    save(HERE/"input_lock.json",{"protocol_sha":sha((HERE/"PROTOCOL.md").read_bytes()),"inputs_sha":sha((HERE/"inputs.json").read_bytes()),
         "old_ids":[x["id"] for x in its if x["panel"]=="old"],"fresh_ids":[x["id"] for x in its if x["panel"]=="fresh"],
         "sources":{f:sha((OLD/f).read_bytes()) for f in ("mbppplus.jsonl.gz","upstream-sanitized-mbpp.json","roster.json","cap1024/roster.json")}})
    print([(p,len([r for r in its if r["panel"]==p])) for p in ("old","fresh")])
if __name__=="__main__":main()

