"""Reuse frozen functions and weights for the disjoint replication without rewriting the first panel."""
import collections,concurrent.futures,hashlib,json,shutil,sys
from pathlib import Path
import prefix,rank,navigation,pr_oracle,grade
HOME=Path(__file__).resolve().parent;S=HOME/'replication'
REPOS="adamchainz/flake8-comprehensions brazilian-utils/brutils-python Delgan/loguru HypothesisWorks/hypothesis ipython/traitlets pallets/click pypa/setuptools python-attrs/attrs s-knibbs/dataclasses-jsonschema scikit-build/scikit-build-core theacodes/nox".split()
def bind():
    for m in (prefix,rank,navigation,pr_oracle,grade):m.D=S
def prepare():
    bind();mainlock=json.loads((HOME/'forecast.lock.json').read_bytes())
    assert mainlock['files']['rank.py']==prefix.h((HOME/'rank.py').read_bytes())
    shutil.copyfile(HOME/'rank.py',S/'rank.py')
    upstream=prefix.ext.get(prefix.V/'memory-stage-fetch/source-manifest.json')
    named={v['rfilename']:v for v in upstream['siblings']};roster=[]
    assert not set(REPOS)&set(prefix.ext.REPOSITORIES)
    for repo in REPOS:
        for f in sorted((prefix.V/'benchmark/history/python'/repo.replace('/','__')).glob('*/*.traj.json')):
            blob=f.read_bytes();key=f.relative_to(prefix.V/'benchmark').as_posix();rec=named[key]
            expected=rec.get('lfs',{}).get('sha256') or rec['blobId']
            actual=prefix.h(blob) if len(expected)==64 else hashlib.sha1(b'blob '+str(len(blob)).encode()+b'\0'+blob).hexdigest()
            assert actual==expected
            msgs=json.loads(blob)['messages'];issue=next((m['content'] for m in msgs if m['role']=='user'),'').partition('</pr_description>')[0]
            if prefix.ext.BAD.search(issue):continue
            roster.append(dict(iid=f.parent.name,repo=repo,file=key,sha=prefix.h(blob),upstream=expected))
    rows=[]
    for rec in roster:rows.extend(prefix.sample(rec))
    prefix.save('roster.json',roster);prefix.save('inputs.json.gz',rows)
    prefix.save('input.lock.json',{'study':{n:prefix.h((S/n).read_bytes()) for n in ('PROTOCOL_RU.md','roster.json','inputs.json.gz','rank.py')},'split':{'dev':[],'external':REPOS},'code_parent':{n:prefix.h((HOME/n).read_bytes()) for n in ('prefix.py','rank.py','navigation.py','pr_oracle.py','grade.py','replicate.py')},'histories':len(roster),'anchors':len(rows),'tasks_with_anchors':len({r['iid'] for r in rows})})
    rank.main();print('replication input',len(roster),len(rows),flush=True)
def metadata():
    import pyarrow.parquet as pq
    tab=pq.read_table('D:/CodexResearch/x20-round12-negative-objects/SWE-rebench-V2.parquet',columns=['instance_id','repo','base_commit'])
    bind();ids={x['iid'] for x in prefix.get('roster.json')};selected={r['instance_id']:r for r in tab.to_pylist() if r['instance_id'] in ids}
    assert set(selected)==ids
    prefix.save('official_base.json',selected)
def patch():
    bind();navigation.verify_lock();(S/'pr_refs').mkdir(exist_ok=True);original=prefix.get('official_base.json')
    pairs=sorted({(q['iid'],q['repo']) for q in prefix.get('inputs.json.gz')})
    with concurrent.futures.ThreadPoolExecutor(5) as pool:rs=list(pool.map(pr_oracle.meta,pairs))
    groups=collections.defaultdict(list)
    for r in rs:
        if r['status']=='ok':r['base']=original[r['iid']]['base_commit'];groups[r['repo']].append(r)
    with concurrent.futures.ThreadPoolExecutor(4) as pool:
        for _ in pool.map(pr_oracle.fetch,groups.items()):pass
    prefix.save('patch_labels.json.gz',rs);print('PR refs',len(rs))
def nav():
    bind();navigation.main()
def score():
    bind();grade.main()
if __name__=='__main__':{'freeze':prepare,'meta':metadata,'patch':patch,'nav':nav,'score':score}[sys.argv[1]]()
