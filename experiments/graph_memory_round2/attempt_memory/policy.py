"""Program -> probe -> observed output graph; value of one fallible evidence lookup."""
import math, re, sys
from collections import defaultdict,Counter
from prepare import HERE,read,save,sha
from llm import model_call
ACTIVE=("uniform","short","gini","value","placebo")

def candidates(row):
    high=max(x["public"] for x in row["arms"])
    sub=[x for x in row["arms"] if x["public"]==high]
    groups=defaultdict(list)
    for a in sub:groups[tuple(a["vec"])].append(a["j"])
    return [(vec,slots,math.sqrt(len(slots))/sum(math.sqrt(len(s)) for s in groups.values())) for vec,slots in groups.items()]

def design(r):
    groups=candidates(r)
    choices=[]
    for idx,probe in enumerate(r["probes"]):
        vals=[g[0][idx] for g in groups]
        if None in vals or len(set(vals))<2:continue
        options=sorted(set(vals),key=lambda o:sha(f"label|{r['id']}|{probe}|{o}"))
        L=len(probe)+sum(len(x) for x in options)
        reliability=.56+.39/(1+L/80)
        def likelihood(i,y):
            return reliability if vals[i]==y else (1-reliability)/(len(options)-1)
        val=sum(max(g[2]*likelihood(i,y) for i,g in enumerate(groups)) for y in options)
        gini=1-sum(sum(g[2] for i,g in enumerate(groups) if vals[i]==y)**2 for y in options)
        choices.append(dict(idx=idx,probe=probe,opts=options,length=L,r=reliability,voi=val,gini=gini,
                            order=sha(f"select|{r['id']}|{probe}")))
    sel={}
    if choices:
        sel["uniform"]=min(choices,key=lambda t:t["order"])
        sel["short"]=min(choices,key=lambda t:(t["length"],t["order"]))
        sel["gini"]=min(choices,key=lambda t:(-round(t["gini"],12),t["order"]))
        sel["value"]=min(choices,key=lambda t:(-round(t["voi"],12),t["length"],t["order"]))
        sel["placebo"]=sel["value"]
    return groups,choices,sel

def lookup(r,c):
    system="You check the intended behavior of a small pure Python function. Choose the correct listed value for the given arguments. If the inputs violate the specification, or no single listed value can be justified, answer U. Reply with exactly one letter."
    opts="\n".join(chr(65+i)+". "+v for i,v in enumerate(c["opts"]))
    user="Specification: "+r["spec"]+"\nInterface: "+r["sig"]+"\nPositional arguments as a tuple: "+c["probe"]+"\nPossible results:\n"+opts+"\nU. Unknown or unspecified"
    seed=int(sha("testreader|"+str(r["id"])+"|"+c["probe"])[:7],16)
    rec=model_call(system,user,8,seed,0)
    msg=rec["reply"]["choices"][0]["message"].get("content") or ""
    m=re.fullmatch(r"\s*([A-CU])[.)]?\s*",msg,re.I)
    idx=ord(m.group(1).upper())-65 if m else -1
    return {"choice":idx if 0<=idx<len(c["opts"]) else None,"reply":msg,"key":rec["key"],"usage":rec["reply"]["usage"]}

def main():
    panel=sys.argv[1]
    rows=read(HERE/("observed_"+panel+".json"));out=[]
    for row in rows:
        groups,available,sel=design(row)
        static=min(groups,key=lambda g:(-g[2],g[1][0]))[1][0]
        decisions={"single":0,"first_public":groups[0][1][0],"static":static}
        uses={};calls={}
        for name in ACTIVE:
            c=sel.get(name)
            if not c:
                decisions[name]=static;continue
            idx=c["idx"]
            if idx not in calls:calls[idx]=lookup(row,c)
            ans=calls[idx]["choice"]
            if ans is None:decisions[name]=static
            else:
                if name=="placebo":ans=(ans+1)%len(c["opts"])
                y=c["opts"][ans]
                def post(g):
                    return g[2]*(c["r"] if y==g[0][idx] else (1-c["r"])/(len(c["opts"])-1))
                decisions[name]=min(groups,key=lambda g:(-post(g),g[1][0]))[1][0]
            uses[name]=idx
        out.append({"id":row["id"],"panel":panel,"groups":len(groups),"admissible":available,"used":uses,"answers":calls,"decisions":decisions})
    path=HERE/("decisions_"+panel+".json");save(path,out)
    print(panel, "items",len(rows),"informative",sum(bool(p["used"]) for p in out),"unique lookups",sum(len(p["answers"]) for p in out),"sealed",sha(path.read_bytes()))
if __name__=="__main__":main()

