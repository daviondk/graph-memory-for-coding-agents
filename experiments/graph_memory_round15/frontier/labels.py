"""Separate evaluator. Project official patch files to old paths only after the forecast was sealed."""
from frontier import *
import pr_oracle
import pyarrow.parquet as pq
BENCH=Path('D:/CodexResearch/x20-round12-negative-objects/SWE-rebench-V2.parquet')

def verify():
    assert all(h((D/n).read_bytes())==d for n,d in read(D/'forecast.lock.json').items())

def project_patch(patch):
    active=False;old=None;new=None;paths=set()
    # Restrict to file headers before the first hunk so removed code cannot forge a header.
    for line in patch.splitlines():
        if line.startswith('diff --git '):
            active=True;old=None;new=None
        elif active and line.startswith('--- '):old=line[4:].split('\t',1)[0]
        elif active and line.startswith('+++ '):
            new=line[4:].split('\t',1)[0]
            if old and old.startswith('a/') and pr_oracle.production(old[2:]):paths.add(old[2:])
            active=False
        elif line.startswith('@@'):active=False
    return sorted(paths)

def bench_labels(ids):
    out={}
    pf=pq.ParquetFile(BENCH)
    for b in pf.iter_batches(batch_size=200,columns=['instance_id','base_commit','patch']):
        for r in b.to_pylist():
            if r['instance_id'] in ids:
                paths=project_patch(r['patch'])
                out[r['instance_id']]={'base':r['base_commit'],'prod':paths,'patch_sha':h(r['patch'].encode())}
    assert set(out)==ids,(len(out),len(ids))
    return out

def nav(row,steps):
    j=row['index']; assert steps[j][2]==row['id'].split('|',1)[1]
    for idx,mi,cid,cmd,tool in steps[j+1:j+6]:
        rc,shown=prefix.shown(tool)
        if rc!=0 or not shown:continue
        views=prefix.inspect(cmd,shown,row['repo'])
        if len(views)==1:
            root,p,kind,_=views[0]
            if kind!='grep-list' and root==row['key']['root']:return p
    return None

def main():
    verify(); inp=read(D/'frontier_inputs.json.gz');roster=read(D/'rosters.json.gz')
    ordered={};record={}
    gt={n:read(d/'patch_labels.json.gz') for n,d in [('primary',R),('replication',R/'replication')]}
    gt['grounded_all']=read(G/'patch_labels.gz');gt['external']=[]
    bmk=bench_labels({r['iid'] for rs in inp.values() for r in rs})
    for panel,rows in inp.items():
        strict={r['iid']:r for r in gt[panel] if r['status']=='ok' and r['strict']}
        oldnav={}
        if panel in ('primary','replication'):
            d=R if panel=='primary' else R/'replication'
            oldnav={r['id']:r['target']['path'] if r['target'] else None for r in read(d/'navigation_labels.json.gz')}
        if panel=='grounded_all':oldnav={k:(v['target']['path'] if v['target'] else None) for k,v in read(G/'navigation_labels.gz').items()}
        navs={};groups=collections.defaultdict(list)
        for r in rows:groups[r['iid']].append(r)
        for rr in roster[panel]:
            if rr['iid'] not in groups:continue
            raw=(prefix.V/'benchmark'/rr['file']).read_bytes();assert h(raw)==rr['sha']
            steps=list(prefix.calls(json.loads(raw)['messages']))
            navs.update({r['id']:nav(r,steps) for r in groups[rr['iid']]})
        assert all(navs[k]==v for k,v in oldnav.items())
        out=[]
        for r in rows:
            iid=r['iid'];sid=r['id']
            s=strict.get(iid)
            if s:assert bmk[iid]['base']==s['base']
            orig=[] if s is None else s['prod']
            out.append({'id':sid,'iid':iid,'repo':r['repo'],'patch_strict':orig,'strict_available':s is not None,
                        'patch_official':bmk[iid]['prod'],'next':[navs[sid]] if navs[sid] else []})
        ordered[panel]=out;record[panel]={'old_navigation_rows_verified':len(oldnav),'known_strict_tasks':len(strict),
                          'available_official':len(groups),'tasks_equal_file_sets_when_strict':sum(set(s['prod'])==set(bmk[k]['prod']) for k,s in strict.items())}
    save('outcomes.json.gz',ordered);save('official_patch_paths.json.gz',bmk)
    hh=hashlib.sha256()
    with BENCH.open('rb') as stream:
        for part in iter(lambda:stream.read(8*1024*1024),b''):hh.update(part)
    sources={str(p):h(p.read_bytes()) for p in [R/'patch_labels.json.gz',R/'replication/patch_labels.json.gz',G/'patch_labels.gz',
        R/'navigation_labels.json.gz',R/'replication/navigation_labels.json.gz',G/'navigation_labels.gz']}
    save('outcome.lock.json',{'forecast_lock':h((D/'forecast.lock.json').read_bytes()),'originals':sources,
       'official_parquet_sha256':hh.hexdigest(),'official_parquet_bytes':BENCH.stat().st_size,'panels':record,
       'files':{n:h((D/n).read_bytes()) for n in ('labels.py','outcomes.json.gz','official_patch_paths.json.gz')}})
    print(record)
if __name__=='__main__':main()
