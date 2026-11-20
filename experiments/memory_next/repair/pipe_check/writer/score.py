"""Compute first-token-independent exact classification against shell sidecars."""
from collections import Counter
import csv
import json
import math
import re
import zipfile
from prepare import CHECK,HERE,save,read,sha

LABELS='ABCDE'
def native_label(status,modes):
    if 1 in status:return 'A'
    if any(rc in (2,3,4,5,6) for rc in status):return 'B'
    if not status or any(rc!=0 for rc in status):return 'E'
    return 'D' if all(modes) else 'C'

def decoder(rows):
    states=[{0:'collect' if r['collect_only'] else 'pass',1:'failure',2:'runner',3:'runner',4:'runner',5:'runner',6:'runner'}.get(r['native_rc'],'unknown') for r in rows]
    for k,label in [('failure','A'),('runner','B'),('unknown','E'),('pass','C'),('collect','D')]:
        if k in states:return label
    return 'E'
def metrics(rows,rule):
    cm={x:{y:0 for y in LABELS+'!'} for x in LABELS}
    for r in rows:cm[r['truth']][r[rule]]+=1
    n=len(rows);right=sum(cm[x][x] for x in LABELS)
    covered=sum(r[rule] in 'ABCD' for r in rows);correct_claim=sum(r[rule] in 'ABCD' and r[rule]==r['truth'] for r in rows)
    supports={x:sum(cm[x].values()) for x in LABELS}
    return {'n':n,'correct':right,'accuracy':right/n,'claims':covered,'coverage':covered/n,'correct_claims':correct_claim,'accuracy_of_claims':(correct_claim/covered if covered else None),
            'false_passed':sum(r[rule]=='C' and r['truth']!='C' for r in rows),'macro_recall_present':sum(cm[x][x]/supports[x] for x in LABELS if supports[x])/sum(bool(v) for v in supports.values()),
            'invalid':sum(cm[x]['!'] for x in LABELS),'confusion':cm}
def main():
    lock=read(HERE/'calls_lock.json');assert lock['model_calls_sha256']==sha(HERE/'model_calls.jsonl')
    rec={r['key']:r for r in map(json.loads,(HERE/'model_calls.jsonl').read_text(encoding='utf8').splitlines())}
    assert len(rec)==40
    payloads=read(HERE/'payloads.json')
    rows=[]
    with zipfile.ZipFile(CHECK/'raw.zip') as z:
        for i in range(1,21):
            pre='raw/%02d/'%i
            info=json.loads(z.read(pre+'design.json'))
            statuses=[int(x.split('\t')[2].split()[0]) for x in z.read(pre+'instrumented/pipeline.tsv').decode().splitlines()]
            modes=['--collect-only' in p['args'] for p in info['pipelines']]
            gt=native_label(statuses,modes)
            keys={a:f'{i:02d}_{a}' for a in ('hidden','measured')}
            fields=json.loads(payloads[keys['measured']]['messages'][1]['content'])['pytest_invocations_in_order']
            r={'command':i,'issue':info['id'],'solver_arm':info['arm'],'turn':info['turn'],'truth':gt,'always_fail':'A',
               'regex':'A' if bool(info['failure_evidence']) else 'E','decoder':decoder(fields)}
            for a,key in keys.items():
                raw=(rec[key]['raw'] or '').strip();r[a]=raw if re.fullmatch('[ABCDE]',raw) else '!'
            rows.append(r)
    names=('hidden','measured','always_fail','regex','decoder')
    summary={k:metrics(rows,k) for k in names}
    dif=[int(r['measured']==r['truth'])-int(r['hidden']==r['truth']) for r in rows]
    w,l=dif.count(1),dif.count(-1);n=w+l
    p=min(1.,2*sum(math.comb(n,k) for k in range(min(w,l)+1))/2**n) if n else 1.
    cluster={}
    for iid in sorted({r['issue'] for r in rows}):
        sub=[r for r in rows if r['issue']==iid]
        cluster[iid]={'n':len(sub),**{k:metrics(sub,k)['correct'] for k in names}}
    usage={a:{k:sum(r['usage'][k] for r in rec.values() if r['arm']==a) for k in ('prompt_tokens','completion_tokens','total_tokens')} for a in ('hidden','measured')}
    res={'methods':summary,'rows':rows,'classes':dict(Counter(r['truth'] for r in rows)),
         'paired':{'wins':w,'losses':l,'ties':len(dif)-n,'descriptive_sign_test_p':p},'per_issue':cluster,'usage':usage}
    save(HERE/'results.json',res)
    with (HERE/'per_action.csv').open('w',newline='',encoding='utf8') as f:
        out=csv.DictWriter(f,fieldnames=list(rows[0]));out.writeheader();out.writerows(rows)
    print({k:s['correct'] for k,s in summary.items()},res['paired'],usage,flush=True)
if __name__=='__main__':main()

