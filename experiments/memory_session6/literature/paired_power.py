"""Illustrative exact paired-binary power in independent tasks; does not estimate a treatment effect."""
import json
from pathlib import Path

import numpy as np

ROOT=Path(__file__).resolve().parent
HORIZON=1600

def advance(a,p):
    b=np.zeros(len(a)+1)
    b[:-1]+=(1-p)*a
    b[1:]+=p*a
    return b

def scenario(win,loss):
    q=win+loss
    null=np.array([1.]);alternative=np.array([1.]);n_disc=np.array([1.])
    cond=[0.];power={}
    first=None
    for n in range(1,HORIZON+1):
        null=advance(null,.5);alternative=advance(alternative,win/q);n_disc=advance(n_disc,q)
        lower=np.cumsum(null)
        reject=2*np.minimum(lower,lower[::-1])<=.05+1e-14
        cond.append(float(sum(alternative[reject])))
        value=float(np.dot(np.asarray(cond),n_disc))
        if n in [40,100,200,400,800,1600]:power[str(n)]=value
        if first is None and value>=.80:first=n
    return {'win_probability':win,'loss_probability':loss,'power':power,'first_n_reaching_80_percent':first}

def main():
    result={'assumptions':'Independent paired questions; a two-sided exact conditional sign test at 0.05. Hypothetical win/loss probabilities; no adjustment for clustered repositories, missing judgments or multiple comparisons.','scenarios':[scenario(.10,.05),scenario(.15,.10),scenario(.12,.02)]}
    p=ROOT/'paired_power.json'
    if p.exists():assert json.loads(p.read_bytes())==result
    else:p.write_text(json.dumps(result,indent=2),encoding='utf8')
    print([(r['win_probability'],r['loss_probability'],round(r['power']['40'],3),r['first_n_reaching_80_percent']) for r in result['scenarios']])
if __name__=='__main__':main()
