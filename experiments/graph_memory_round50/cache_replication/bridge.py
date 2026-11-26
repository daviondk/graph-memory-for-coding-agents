"""Validate a metadata bridge on raw, unaugmented calibration prefixes only."""
from lineage import *
PLAN2='61319a763aaf63704ba52059cdfc1d28fa0dd9abf03f049be6b1b34619b71566'
def main():
    assert sha(D/'ORIGINAL_IDS_RU.md')==PLAN2 and not rd(D/'selection.json')['gate']
    source=rd(FROZEN/'inputs.json.gz');original={q for q in source if re.search(r'-s\d+$',q)}
    pred,cstat=process('cal500',original);test=rd(D/'test-panel.json.gz')
    assert all(re.search(r'-s\d+$',q) for q in test)
    raw={};clusters=collections.defaultdict(list)
    excluded={}
    with gzip.open(PUB/'cal500/items.jsonl.gz','rt',encoding='utf8') as f:
        for item in map(json.loads,f):
            q=item['state_id']
            if q not in original:continue
            events=item['trajectory_prefix'];run={e.get('run_id') for e in events}
            key=(item['repo'],item['instance_id'],item['base_commit'],next(iter(run)) if len(run)==1 and next(iter(run),None) else q)
            raw[q]=[h(json.dumps(e,sort_keys=True,separators=(',',':'),ensure_ascii=False)) for e in events];clusters[key].append(q)
    rows={}
    for group in clusters.values():
        for q in group:
            prior={}
            for p in group:
                before=raw[p];end=raw[q]
                if before and len(before)<len(end) and before==end[:len(before)]:
                    k=tuple(before)
                    if k not in prior or h('r48-representative'+p)<h('r48-representative'+prior[k]):prior[k]=p
            truth=[prior[k] for k in sorted(prior,key=len)]
            rows[q]=dict(true=truth,pred=pred[q]['prior'],panel=source[q]['panel'])
    stats={}
    for label in ['R48','R49','both']:
        rr=[v for v in rows.values() if label=='both' or v['panel']==label]
        trial=[v for v in rr if v['pred']]
        stats[label]=dict(states=len(rr),proposed=len(trial),true=sum(bool(v['true']) for v in rr),
            matching_parent=sum(v['pred'][-1:]==v['true'][-1:] for v in trial),matching_complete=sum(v['pred']==v['true'] for v in trial))
    v=stats['both'];ok=v['proposed']>=50 and min(v['matching_parent'],v['matching_complete'])/v['proposed']>=.98
    dump('bridge-cal.json.gz',rows);dump('bridge.json',dict(plan=PLAN2,stats=stats,gate=ok,original_test=len(test),test_scope=sha(D/'test-panel.json.gz')))
    print(stats,'usable',ok)
if __name__=='__main__':main()

