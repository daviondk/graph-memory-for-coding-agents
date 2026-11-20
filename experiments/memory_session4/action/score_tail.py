import json
from collections import defaultdict
from run import P,readgz
from evaluate import boot
def main():
    pred=readgz(P/'tail_predictions.jsonl.gz');x={r['id']:r for r in readgz(P/'tail_inputs.jsonl.gz')}
    y={r['id']:r for r in readgz(P/'tail_labels.jsonl.gz')};n=len(pred)
    arms=sorted({k for r in pred for k in r['selected']});rates={}
    for a in arms:
        chosen=[r for r in pred if a in r['selected']]
        rates[a]={'brier':sum((r['p'][a]-y[r['id']]['passed'])**2 for r in pred)/n,
             'selected':len(chosen),'recovered':sum(y[r['id']]['passed'] for r in chosen),
             'hours':sum(y[r['id']]['duration_s'] for r in chosen)/3600}
    paired={}
    for a,b in [('typed','repo_status'),('typed','global_type'),('typed','glm_type'),('glm_type','glm'),('typed_if_uncertain','typed')]:
        bs=defaultdict(lambda:[0,0]);gain=defaultdict(lambda:[0,0])
        for r in pred:
            i=r['id'];rp=x[i]['repo'];z=y[i]['passed']
            bs[rp][0]+=(r['p'][a]-z)**2-(r['p'][b]-z)**2;bs[rp][1]+=1
            gain[rp][0]+=(int(a in r['selected'])-int(b in r['selected']))*z;gain[rp][1]+=1
        paired[a+' vs '+b]={'brier':boot(bs),'rescues':boot(gain)}
    result={'n':n,'projects':len({x[r['id']]['repo'] for r in pred}),'recoveries':sum(y[r['id']]['passed'] for r in pred),
        'time_start':min(x[r['id']]['decision_at'] for r in pred),'time_end':max(x[r['id']]['decision_at'] for r in pred),
        'reads':{'always':n,'uncertain':sum(r['p']['uncertain'] for r in pred),'sparse':sum(r['p']['sparse'] for r in pred)},
        'rates':rates,'paired':paired}
    import sys
    if '--check' in sys.argv:assert result==json.loads((P/'tail_results.json').read_bytes())
    else:(P/'tail_results.json').write_text(json.dumps(result,indent=1,sort_keys=True))
    print('verified tail scores',n)
if __name__=='__main__':main()
