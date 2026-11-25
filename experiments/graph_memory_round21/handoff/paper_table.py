"""Reconstruct integer numerators uniquely consistent with the published rounded percentages."""
import json
from pathlib import Path
# Section 3.4 Table 1, source/worker/lead/final/judge (%), n=146 observations/model/policy.
PAPER='https://arxiv.org/html/2611.22245v2#S3.T1'
rows={
'5.6':{'none':[69.9,None,69.9,21.2,15.8],'optional':[67.1,.7,63.0,26.0,23.3],'required':[78.8,24.0,24.0,11.6,10.3]},
'6':{'none':[59.6,None,59.6,17.8,17.1],'optional':[65.1,.7,63.7,19.9,19.2],'required':[61.6,18.5,18.5,12.3,11.6]},
'haiku':{'none':[21.2,None,21.2,15.8,15.8],'optional':[56.2,37.0,37.7,31.5,30.1],'required':[65.8,30.8,30.8,23.3,17.8]}}
published={'none':[50.2,None,50.2,18.3,16.2],'optional':[62.8,12.8,54.8,25.8,24.2],'required':[68.7,24.4,24.4,15.8,13.2]}
def invert(p,n):
    if p is None: return None
    vals=[k for k in range(n+1) if abs(100*k/n-p)<.05]
    assert len(vals)==1
    return vals[0]
def main():
    numerators={m:{a:[invert(p,146) for p in row] for a,row in model.items()} for m,model in rows.items()}
    pooled={a:[invert(p,438) for p in row] for a,row in published.items()}
    for a,row in pooled.items():
        for j,n in enumerate(row):
            if n is not None: assert sum(numerators[m][a][j] for m in numerators)==n
    assert pooled['required'][:3]==[301,107,107]
    # Intersection count explicitly given in section 4.3, not inferable from the margins alone.
    intersection=106; source,worker=pooled['required'][:2]
    contingency={'source_and_worker':intersection,'source_only':source-intersection,'worker_only':worker-intersection,'neither':438-source-worker+intersection,'retention_conditional':intersection/source}
    Path(__file__).with_name('paper-table-audit.json').write_text(json.dumps(dict(source=PAPER,columns=['source','worker','lead','final','judge'],denominator_per_model_policy=146,model_rows=numerators,pooled=pooled,required_intersection=contingency),indent=2)+'\n')
if __name__=='__main__': main()

