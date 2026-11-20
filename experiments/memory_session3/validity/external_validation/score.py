"""Join frozen masks with the independently executed current-version values."""
import collections,csv,gzip,io,json,statistics,sys
from sources import ROOT,canon,sha,save
def j(p):return json.loads(p.read_text(encoding='utf8'))
def rr(p):
    with p.open(encoding='utf8',newline='') as f:return list(csv.DictReader(f))
def project():
    plain={};traces={};dur=collections.defaultdict(lambda:collections.Counter())
    for f in sorted((ROOT/'runs').glob('*/*/plain.json')):
        pkg,v=f.parent.parent.name,f.parent.name;ind={r['key']:r for r in j(f)}
        for r in j(f.parent/'traced.json'):
            k=r['key'];v1=ind[k];assert r['entry']==v1['entry'] and v1['value']==r['value'],(pkg,v,k)
            plain[pkg,v,k]=sha(canon(v1['value']).encode())
            dur[pkg]['plain_ns']+=v1['run_ns'];dur[pkg]['trace_ns']+=r['run_ns']
            dur[pkg]['plain_load_ns']+=v1['load_ns'];dur[pkg]['trace_load_ns']+=r['load_ns']
            dur[pkg]['n']+=1
    return plain,dur
def build(require_all):
    lock=j(ROOT/'prediction_lock.json')
    for f,h in lock['sha256'].items():assert sha((ROOT/f).read_bytes())==h
    plain,durations=project()
    decisions=rr(ROOT/'decisions.csv');out=[]
    sets={};comparators={}
    configs=['testmon','testmon_normal']
    for name in configs:
        issues=[];n=0;canary=[];sec={'old':0,'new':0}
        for f in (ROOT/name).glob('*/*/run.json'):
            pkg=f.parent.parent.name;old,new=f.parent.name.split('--');d=j(f);n+=1
            for phase,v in [('old',old),('new',new)]:
                sec[phase]+=d[phase]['wall_seconds']
                for key,h in d[phase]['oracle_hashes'].items():
                    if plain[pkg,v,key]!=h:issues.append([pkg,v,key,phase])
            if 'unchanged' in d:canary.append([pkg,len(d['unchanged']['executed'])])
            sets[name,pkg,old,new]=set(d['new']['executed'])
        comparators[name]={'pairs':n,'observed_disagreements':issues,'unchanged_calibration_executed':canary,'seconds':sec}
        if require_all:assert n==28 and not issues,(name,n,issues[:3])
    for d in decisions:
        pkg,old,new,key=[d[z] for z in ['pkg','old','new','key']]
        change=plain[pkg,old,key]!=plain[pkg,new,key]
        row={'pkg':pkg,'old':old,'new':new,'key':key,'changed':int(change)}
        for m,x in d.items():
            if m not in row:row[m]=int(x=='True')
        for m in configs:
            if (m,pkg,old,new) in sets:row[m]=int(key not in sets[m,pkg,old,new])
        out.append(row)
    return out,durations,comparators
def counts(rows,m):
    valid=[r for r in rows if m in r];n=len(valid);reuse=sum(r[m] for r in valid);stale=sum(r[m]*r['changed'] for r in valid);changed=sum(r['changed'] for r in valid)
    return {'n':n,'changed':changed,'rerun':n-reuse,'reuse':reuse,'correct_reuse':reuse-stale,'stale_reuse':stale,'redundant_rerun':n-reuse-changed+stale,'caught_change':changed-stale}
def compute(rows,dur,cmp):
    groups={'all':rows}
    for pkg in sorted(set(r['pkg'] for r in rows)):groups[pkg]=[r for r in rows if r['pkg']==pkg]
    arms=['always_replay','always_reuse','direct_file','dynamic_files','scopes','scopes_guards','observed_branches_guards','testmon','testmon_normal']
    return {'groups':{k:{m:counts(v,m) for m in arms} for k,v in groups.items()},'timing':dict(dur),'comparators':cmp}
def main():
    partial='--partial' in sys.argv
    rows,t,c=build(not partial);z=compute(rows,t,c);save(ROOT/('provisional.json' if partial else 'results.json'),z)
    if not partial:
        with (ROOT/'per_check.csv').open('w',encoding='utf8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print(z['groups']['all'])
if __name__=='__main__':main()

