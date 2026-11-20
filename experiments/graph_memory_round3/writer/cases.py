"""Choose examples by a fixed hash among wins and losses, then recover only file/line bounds."""
import sys
from replay import D,DATA,old,rows,save
sys.path.insert(0,str(D))
from score import locations
from pipeline import future
def intervals(nums):
    out=[]
    for n in sorted(nums):
        if out and n==out[-1][1]+1:out[-1][1]=n
        else:out.append([n,n])
    return out
def main():
    rs=list(rows(D/"per_cut.jsonl.gz"));examples={}
    for label,sign in [("graph_win",1),("graph_loss",-1)]:
        candidates=[r for r in rs if r[3]["typed@4096"][0]-r[3]["point@4096"][0]==sign and r[2]>12]
        i,t,*_=min(candidates,key=lambda r:old.e.sha("round3example|"+str(r[:2])))
        for k in range(8):
            o=next((r for r in rows(DATA/f"source_{k}.jsonl.gz") if r["instance"]==i),None)
            if o is None:continue
            q=future(o["events"],t);entry=next(r for r in rows(D/f"sealed_{k}.jsonl.gz") if r[0]==i)
            _,catalog,cuts,usage=entry;state=dict(cuts)[t]
            target=locations([catalog[j] for j in state["unbounded@0"]],q[0],q[1]);result={}
            for a in ["typed@4096","point@4096","lru@4096"]:
                cache={n:s for j in state[a] for p,lo,hi,body in [catalog[j]] if p==q[0] for n,s in enumerate(body.split("\n"),lo)}
                result[a]=intervals(n for n,s in target if cache.get(n)==s)
            examples[label]=dict(instance=i,step=t,file=q[0],required=[target[0][0],target[-1][0]],retained_target_lines=result)
            break
    save(D/"cases.json",examples)
if __name__=="__main__":main()
