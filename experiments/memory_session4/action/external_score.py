"""Descriptive modern external cohort, with every attrition category explicit."""
from collections import Counter
from pathlib import Path
import json
P=Path(__file__).resolve().parent/'github'
def main():
    rs={}
    for f in P.glob('index-*'):
        for row in json.loads(f.read_bytes())['rows']:rs[row['id']]=row
    selected=json.loads((P/'roster.json').read_bytes());counts=Counter();pairs=[];reason=Counter()
    for repo,i in selected:
        f=P/('attempt-'+str(i)+'.json')
        if not f.exists():counts['attempt_lookup_missing']+=1;continue
        z=json.loads(f.read_bytes())
        if z['status']!=200:counts['HTTP_'+str(z['status'])]+=1;continue
        old=z['rows'][0];new=rs[i]
        if old['id']!=new['id'] or old['head_sha']!=new['head_sha'] or old['workflow_id']!=new['workflow_id']:counts['identity_mismatch']+=1;continue
        if not (old['run_attempt']==1 and new['run_attempt']==2 and old['status']==new['status']=='completed'):counts['attempt_state_mismatch']+=1;continue
        if old['conclusion'] not in ('failure','timed_out') or new['conclusion'] not in ('failure','timed_out','success'):
            counts['excluded_'+str(old['conclusion'])+'→'+str(new['conclusion'])]+=1;continue
        if old['updated_at']>new['run_started_at']:counts['nonchronological']+=1;continue
        row={'repo':repo,'id':i,'first':old['conclusion'],'second':new['conclusion'],'head_sha':old['head_sha']}
        pairs.append(row);counts['eligible']+=1
    result={'pages':len(list(P.glob('index-*'))),'index_records':len(rs),'two_attempt_roster':len(selected),
            'retrieved':len(list(P.glob('attempt-*'))),'counts':counts,'eligible_projects':len({r['repo'] for r in pairs}),'pairs':pairs,
            'minimum_required_positive_and_negative_5_each':False,'comparative_estimate':'not_supported_small_purposive_sample'}
    (P/'results.json').write_text(json.dumps(result,indent=1))
    print('external',counts)
if __name__=='__main__':main()
