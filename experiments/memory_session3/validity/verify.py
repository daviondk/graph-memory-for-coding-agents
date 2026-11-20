"""Independent audit of raw observations, coverage masks, oracle, testmon IDs and reported totals."""
import argparse
import collections
import csv
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
METHODS = ('always_replay','always_reuse','direct_file','dynamic_files','scopes','scopes_guards','observed_branches_guards')
PLUGINS = ('testmon','testmon_normal')

def read(p):
    return json.loads(p.read_text(encoding='utf8'))

def digest(x):
    return hashlib.sha256(x).hexdigest()

def canonical(value):
    return json.dumps(value,ensure_ascii=True,sort_keys=True,separators=(',',':')).encode()

def rows(p):
    with p.open(encoding='utf8',newline='') as f:
        return list(csv.DictReader(f))

def pairs(row):
    return tuple(row[key] for key in ('pkg','old','new','key'))

def bit(text):
    assert str(text) in ('True','False','0','1')
    return str(text) in ('True','1')

def seals(base,lock):
    for name,h in lock.items():
        assert digest((base/name).read_bytes())==h,(base,name)

def observations(base):
    roster=read(base/'roster.json')
    by_project=collections.defaultdict(set)
    for r in roster:
        assert r['key'] not in by_project[r['pkg']]
        by_project[r['pkg']].add(r['key'])
    values={}
    for rel in read(base/'sources.json'):
        if rel.get('skip'):continue
        pkg,v=rel['pkg'],rel['v']
        directory=base/'runs'/pkg/v
        def obs(mode):
            x=read(directory/(mode+'.json'))
            result={r['key']:r for r in x}
            assert len(result)==len(x) and set(result)==by_project[pkg]
            return result
        plain,traced=obs('plain'),obs('traced')
        for key,r in plain.items():
            t=traced[key]
            assert r['entry']==t['entry'] and canonical(r['value'])==canonical(t['value'])
            values[pkg,v,key]=digest(canonical(r['value']))
    return values

def plugins(base,values):
    schedules={}
    for name in PLUGINS:
        receipts=sorted((base/name).glob('*/*/run.json'))
        assert len(receipts)==28
        controls={}
        for path in receipts:
            pkg=path.parent.parent.name;old,new=path.parent.name.split('--');run=read(path)
            all_old={key for project,v,key in values if project==pkg and v==old}
            assert set(run['old']['executed'])==all_old
            for phase,data in run.items():
                v=new if phase=='new' else old
                ids=data['executed']
                assert len(set(ids))==len(ids) and set(ids)==set(data['oracle_hashes'])
                for key,h in data['oracle_hashes'].items():
                    assert h==values[pkg,v,key],(name,pkg,v,key)
                if phase=='unchanged':controls[pkg]=len(ids)
            selected=set(run['new']['executed'])
            for key in all_old:schedules[name,pkg,old,new,key]=(key not in selected)
        if name=='testmon_normal':
            assert len(controls)==4 and set(controls.values())=={0},controls
    return schedules

def aggregate(records,m):
    n=len(records);reuse=sum(record[m] for record in records)
    changed=sum(record['changed'] for record in records)
    stale=sum(record[m] and record['changed'] for record in records)
    return {'n':n,'reuse':reuse,'rerun':n-reuse,'changed':changed,'correct_reuse':reuse-stale,
            'stale_reuse':stale,'redundant_rerun':n-changed-reuse+stale,'caught_change':changed-stale}

def check_rows(path,values,schedules,age=False):
    predictions={pairs(r):r for r in rows(path/'decisions.csv')}
    gold=rows(path/'per_check.csv')
    assert len(gold)==len(predictions) and {pairs(r) for r in gold}==set(predictions)
    methods=list(METHODS)+(list(PLUGINS) if schedules else [])
    groups=collections.defaultdict(list)
    for row in gold:
        p=pairs(row);pkg,old,new,key=p
        changed=values[pkg,old,key]!=values[pkg,new,key]
        assert changed==bit(row['changed'])
        r={'changed':changed}
        for m in methods:
            decision=schedules[(m,)+p] if m in PLUGINS else bit(predictions[p][m])
            assert decision==bit(row[m]),(p,m)
            r[m]=decision
        for label in (['all',pkg,row['study'],'gap '+row['gap']] if age else ['all',pkg]):groups[label].append(r)
    expected={label:{m:aggregate(records,m) for m in methods} for label,records in groups.items()}
    if age:assert expected==read(path/'results.json')
    else:assert expected==read(path/'results.json')['groups']
    return len(gold)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--with-wheels',action='store_true',help='Also check local archives named in sources.json')
    args=parser.parse_args()
    all_values={}; totals=[]
    for path in [ROOT,ROOT/'external_validation']:
        seals(path,read(path/'observation_lock.json'))
        seals(path,read(path/'prediction_lock.json')['sha256'])
        values=observations(path);all_values.update(values)
        schedule=plugins(path,values) if path==ROOT else {}
        totals.append(check_rows(path,values,schedule))
        if args.with_wheels:
            cache=Path(os.environ.get('MEMORY_VALIDITY_CACHE','D:/CodexResearch/x20-validity-releases'))
            for r in read(path/'sources.json'):
                if not r.get('skip'):assert digest((cache/'wheels'/r['filename']).read_bytes())==r['sha256']
    assert (ROOT/'scope.py').read_bytes()==(ROOT/'external_validation/scope.py').read_bytes()
    assert (ROOT/'predict.py').read_bytes()==(ROOT/'external_validation/predict.py').read_bytes()
    seals(ROOT,read(ROOT/'age/lock.json')['sha256'])
    totals.append(check_rows(ROOT/'age',all_values,{},True))
    assert totals==[4249,1428,14889]
    print('Verified paired observations:',len(all_values),'adjacent main/external + nonadjacent:',totals,
          'official pytest-testmon transition receipts: 56, four unchanged controls.')
if __name__=='__main__':main()
