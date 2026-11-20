"""Planning only. Exact unconditional power for paired binary outcomes, one seed per independent target."""
from pathlib import Path
import json
from math import comb
def mass(x,n,p):
    return comb(n,x)*p**x*(1-p)**(n-x)
def power(n,win,loss):
    u=win+loss
    ans=0.0
    for k in range(1,n+1):
        critical=-1
        tail=0
        for j in range(k//2+1):
            tail+=comb(k,j)
            if 2*tail/(2**k) <=.05: critical=j
            else:break
        if critical>=0:
            p=sum(mass(j,k,win/u)+mass(k-j,k,win/u) for j in range(critical+1))
            ans+=mass(k,n,u)*p
    return ans
if __name__=='__main__':
    result=[]
    for n in (34,111,300):
        for win,loss in ((.10,.05),(.15,.05)):
            result.append({'independent_targets':n,'win':win,'loss':loss,'two_sided_exact_power':power(n,win,loss)})
    p=Path(__file__).resolve().parent/'power-scenarios.json';p.write_text(json.dumps(result,indent=2),encoding='utf8')

