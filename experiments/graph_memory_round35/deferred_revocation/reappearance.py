"""Finite counterfactual: handling an edge that vanishes and returns before a deletion flush."""
from replay import state,update,put,D,MODES
from itertools import product
def main():
    checks=react=0;example=None
    # Every two-edge ground-truth stream of length four. Read after events 2 and 4.
    for history in product(range(4),repeat=4):
        truth=set();seq={a:state() for a in MODES};brute={a:set() for a in MODES}
        for step,mask in enumerate(history,1):
            new={i for i in range(2) if mask&(1<<i)};adds=new-truth;loss=truth-new
            for a,e in seq.items():
                update(e,adds,loss,a,step,step%2==0)
                current=brute[a]|new
                must=(a=="exact" or (a=="periodic4" and step%4==0) or (a=="lazy_read" and step%2==0) or (a=="pending4" and len(current-new)>=4))
                brute[a]=new.copy() if must else current
                assert e["db"]==brute[a] and e["waiting"]==brute[a]-new;checks+=1
            truth=new
        react+=seq["lazy_read"]["s"]["reactivated"]
        if history==(1,1,0,1):
            e=seq["lazy_read"]
            assert e["db"]=={0} and e["s"]["reactivated"]==1 and e["s"]["batches"]==0 and e["s"]["inserts"]==1
            example={"states":history,"inserts":1,"physical_deletes":0,"queued":1,"reactivated":1,"final_active":[0]}
    assert react and example
    put(D/"synthetic.json",dict(histories=4**4,policy_checks=checks,lazy_reactivation_occurrences=react,example=example))
if __name__=="__main__":main()