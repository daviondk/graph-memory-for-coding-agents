from context import D,save,e,rows,stream,line_target,future
def main():
    q=[]
    for r in rows(D/"expansion_scores.jsonl.gz"):
        if r[2]==512:
            a=r[-1]
            if a["iso_balanced"][0]>a["r2f"][0]:q.append((e.sha(f"strict|{r[0]}|{r[1]}"),"iso_gain",r[0],r[1]))
            if a["typed"][0]<a["r2f"][0]:q.append((e.sha(f"drop|{r[0]}|{r[1]}"),"typed_loss",r[0],r[1]))
    picked={name:min(x for x in q if x[1]==name)[2:] for name in ["iso_gain","typed_loss"]};result={}
    for k in range(8):
        pred={ (i,t):ans["512"] for i,t,ans in rows(D/f"expand_pred_{k}.jsonl.gz") if (i,t) in picked.values()}
        for obj in rows(D/f"source_{k}.jsonl.gz"):
            if obj["instance"] not in [v[0] for v in picked.values()]:continue
            for t,rr,idx,_,_,_ in stream(obj):
                key=(obj["instance"],t)
                if key not in pred:continue
                a=pred[key];q=future(obj["events"],t);g=line_target(rr,q[0],q[1])
                name=next(s for s,v in picked.items() if v==key)
                result[name]={"instance":key[0],"cut":t,"needed":g[:3],"r2f":a["r2f"],"alternative":a["iso_balanced" if name=="iso_gain" else "typed"]}
    save("illustrations.json",result)
if __name__=="__main__":main()
