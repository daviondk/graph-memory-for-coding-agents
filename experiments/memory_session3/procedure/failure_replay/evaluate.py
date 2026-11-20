"""Score locked prior-returncode/output forecasts against actual later native outcomes."""
import csv,gzip,json,random,sys
from collections import Counter,defaultdict
from statistics import mean
from forecast import ROOT,sha,ro
def load(n):return json.loads((ROOT/n).read_bytes())
def score(verify):
    lock=load('prediction_lock.json')
    assert all(sha((ROOT/k).read_bytes())==v for k,v in lock['sha256'].items())
    with gzip.open(ROOT/'predictions.jsonl.gz','rt',encoding='utf8') as fp:
        pred={(v['model'],v['issue'],v['group']):v for ln in fp if (v:=json.loads(ln))}
    saved=[];den=Counter();models=defaultdict(Counter);all_issues=set();sixteen=Counter()
    for rel,expected_sha in load('../projected_manifest.json').items():
        raw=(ROOT.parent/rel).read_bytes();assert sha(raw)==expected_sha
        data=json.loads(gzip.decompress(raw));mod=data['source']['model'];id_=data['source']['id'];all_issues.add(id_)
        for i,group in enumerate(data['groups']):
            den['all_calls']+=len(group);models[mod]['all_calls']+=len(group)
            if len(group)!=1:continue
            e=group[0];y=e['result']; cmd=e['command']; isro=bool(cmd) and ro(cmd)
            if cmd and y is not None:
                for key in ['known_single']+(['known_readonly'] if isro else [])+(['observed_nonzero'] if y['rc']!=0 else [])+(['visible_nonzero'] if y['rc']!=0 and y['visible'] else []):
                    den[key]+=1;models[mod][key]+=1
            v=pred.get((mod,id_,i))
            if not v:continue
            assert sha(cmd.encode())==v['cmd_sha']
            for arm,r in v['preds'].items():
                prev=data['groups'][r['at']]
                assert r['at']<i and len(prev)==1 and prev[0]['command']==cmd and prev[0]['result']['visible'] and prev[0]['result']['rc']==r['pred_rc']!=0
                assert r['pred_sha']==prev[0]['result']['sha'] and isro==r['current_readonly']
                actual=y['rc'] if y else None
                saved.append({'arm':arm,'model':mod,'issue':id_,'group':i,'from_group':r['at'],'cmd_sha':v['cmd_sha'],'readonly':isro,'context':r['context'],'past_write':r['past_write'],'changed':r['observed_content_change'],'expected_rc':r['pred_rc'],'rc':actual,'known':int(y is not None),'again':int(actual is not None and actual!=0),'same_rc':int(actual==r['pred_rc']),'same_output':int(bool(y) and y['sha']==r['pred_sha']),'same_pair':int(bool(y) and actual==r['pred_rc'] and y['sha']==r['pred_sha']),'successful':int(actual==0),'bytes':y['bytes'] if y else None})
    index=defaultdict(list)
    for r in saved:
        arm=r['arm'];flags=['all','model_'+r['model'],r['context']]
        if r['readonly']:flags+=['pure','pure_'+r['model'],'pure_'+r['context']]
        if r['past_write']:flags+=['write_since']
        if r['changed']:flags+=['change_since']
        if r['context']=='opaque' and not r['past_write']:flags+=['opaque_no_proven_write']
        for f in flags:index[arm,f].append(r)
    summary={}
    for arm in ['adjacent','guard1','guard8','stale8','history']:
        groups={}
        for flag in sorted({f for a,f in index if a==arm}|{'pure','all','write_since','change_since'}):
            rows=index[arm,flag];valid=[r for r in rows if r['known']]
            issues={r['issue'] for r in valid};insts={(r['issue'],r['model']) for r in valid}
            z={'warnings':len(rows),'scored':len(valid),'issues':len(issues),'sessions':len(insts),'unique_commands':len({r['cmd_sha'] for r in valid}),**{k:sum(r[k] for r in valid) for k in ['again','same_rc','same_output','same_pair','successful']}}
            if flag in ['pure','all','change_since','write_since'] and len(issues)>=10:
                # Resample affected issue clusters, preserving all repeated model-sessions and calls within issues.
                counts={i:[0,0,0] for i in sorted(issues)}
                for r in valid:
                    x=counts[r['issue']];x[0]+=1;x[1]+=r['again'];x[2]+=r['same_pair']
                rng=random.Random(17112026);a=[];b=[];pop=list(counts.values())
                for _ in range(3000):
                    pick=rng.choices(pop,k=len(pop));tot=sum(x[0] for x in pick)
                    a.append(sum(x[1] for x in pick)/tot);b.append(sum(x[2] for x in pick)/tot)
                z['repeat_fail_ci95']=[sorted(a)[74],sorted(a)[2924]];z['joint_ci95']=[sorted(b)[74],sorted(b)[2924]]
            groups[flag]=z
        summary[arm]=groups
    results={'den':den,'den_by_model':dict(models),'unique_issues':len(all_issues),'methods':summary}
    if verify:
        assert results==load('results.json')
        with (ROOT/'casewise.csv').open(encoding='utf8') as f:
            assert list(csv.DictReader(f))==[{k:str(v) if v is not None else '' for k,v in r.items()} for r in saved]
    else:
        with (ROOT/'casewise.csv').open('w',encoding='utf8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(saved[0]));w.writeheader();w.writerows(saved)
        (ROOT/'results.json').write_text(json.dumps(results,indent=1),encoding='utf8')
    print(dict(den),len(pred),'opportunities',len(saved),'arm rows')
    for a,v in summary.items():print(a,[(k,[v[k][z] for z in ['warnings','scored','issues','again','same_rc','same_output','same_pair','successful']]) for k in ['pure','all','write_since','change_since']])
if __name__=='__main__':score('--verify' in sys.argv)

