"""Reconstruct a conservative step order and validate it on the strict calibration lineage."""
import collections,gzip,hashlib,json,re
from pathlib import Path
D=Path(__file__).resolve().parent
FROZEN=D.parent/'cache_prediction';W=D.parents[1];PUB=W/'memory_session5/serbench/upstream/data'
BLIND=W/'graph_memory_round39/blind_export/author_baseline/test500-lexical-residual.jsonl'
PLAN='1789f14a1aaacaf977c8bfba555fb1a66a84bc519a54b70d517ff7e69afc39b0'
def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def h(s):return hashlib.sha256(s.encode()).hexdigest()
def rd(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix=='.gz' else b)
def dump(name,v):
    b=json.dumps(v,sort_keys=True,separators=(',',':')).encode()+b'\n';(D/name).write_bytes(gzip.compress(b,mtime=0) if name.endswith('.gz') else b)
def process(part,allow):
    rows={};groups=collections.defaultdict(list);key_presence=collections.Counter()
    with gzip.open(PUB/part/'items.jsonl.gz','rt',encoding='utf8') as f:
        for item in map(json.loads,f):
            q=item['state_id']
            for k in ('trajectory_prefix','run_id','base_commit','step_id','timestamp','corpus_id'):key_presence[k]+=k in item
            if q not in allow:continue
            j=re.fullmatch(r'(.+)-s(\d+)(?:--[A-Za-z0-9_-]+)?',q)
            src=item.get('base_commit') if part=='cal500' else item.get('corpus_id')
            group=(item['repo'],item['instance_id'],src,j.group(1) if j and src else q)
            gh=h(json.dumps(group));step=int(j.group(2)) if j and src else None
            rows[q]=dict(repo=item['repo'],issue=item['instance_id'],scope=gh,step=step,prior=[])
            groups[gh].append(q)
    ambiguous=0
    for gid,items in groups.items():
        nums=[rows[q]['step'] for q in items]
        if None in nums or len(set(nums))!=len(nums):
            ambiguous+=len(items);continue
        seq=sorted(items,key=lambda q:rows[q]['step'])
        for i,q in enumerate(seq):rows[q]['prior']=seq[:i]
    return rows,dict(states=len(rows),issues=len({a['issue'] for a in rows.values()}),repos=len({a['repo'] for a in rows.values()}),scopes=len(groups),
                     states_with_prior=sum(bool(a['prior']) for a in rows.values()),ambiguous_states=ambiguous,all500_field_presence=key_presence)
def main():
    assert sha(D/'PROTOCOL_RU.md')==PLAN and sha(FROZEN/'manifest.json')=='bb2837a91140d9143a33ca6bea1cb767b0b7d292ab6778d3212635fd5d200237'
    prior=rd(FROZEN/'inputs.json.gz')
    eligible={a['state_id'] for a in map(json.loads,BLIND.open('r',encoding='utf8')) if a['ranked_evidence_ids']}
    cal,cstat=process('cal500',set(prior));test,tstat=process('test500',eligible);assert len(test)==491 and len(cal)==484
    checks={q:dict(pred=v['prior'],true=prior[q]['prev']) for q,v in cal.items()}
    tp=sum(bool(v['pred']) and v['true'][-1:]==v['pred'][-1:] for v in checks.values())
    num=sum(bool(v['pred']) for v in checks.values());gt=sum(bool(v['true']) for v in checks.values())
    exact=sum(bool(v['pred']) and v['true']==v['pred'] for v in checks.values())
    overlap=dict(states=len(cal.keys()&test.keys()),repos=len({r['repo'] for r in cal.values()}&{r['repo'] for r in test.values()}),
                 issues=len({r['issue'] for r in cal.values()}&{r['issue'] for r in test.values()}))
    ok=num>=50 and tp/num>=.98 and not any(overlap.values())
    dump('cal-lineage.json.gz',checks);dump('test-panel.json.gz',test)
    dump('selection.json',dict(protocol=PLAN,cal=cstat,test=tstat,proposed=num,true=gt,matching_parent=tp,matching_complete_prefix=exact,
        parent_precision=tp/num,parent_recall=tp/gt,matches_all_states=sum(v['true']==v['pred'] for v in checks.values()),overlap=overlap,gate=ok,
        model=sha(FROZEN/'models.json'),test_file=sha(PUB/'test500/items.jsonl.gz'),eligibility=sha(BLIND),test_panel=sha(D/'test-panel.json.gz')))
    print('Calibration',tp,num,gt,exact,'gate',ok,'external',tstat,overlap)


if __name__=='__main__':main()

