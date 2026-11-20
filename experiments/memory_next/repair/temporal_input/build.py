"""Time-safe source selector. Only ID and timestamp projections are used to filter."""
from pathlib import Path
import hashlib, json, csv, datetime, re
import concurrent.futures as cf
import requests
import pyarrow as pa
import pyarrow.parquet as pq
import pyarrow.json as pjson

OUT=Path(__file__).resolve().parent
REPAIR=OUT.parent
PREV=REPAIR.parents[1]/'sota_round'/'swe_context'
DATA=Path('D:/CodexResearch/x20-swe-context')
def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def save(n,v):
    tmp=(OUT/n).with_suffix('.tmp')
    tmp.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf8')
    tmp.replace(OUT/n)
def read(p):
    return json.loads(p.read_text(encoding='utf8'))
def parse(t):
    return datetime.datetime.fromisoformat(t.replace('Z','+00:00'))
def url(repo,kind,num):
    return f'https://api.github.com/repos/{repo}/{kind}/{num}'
def fetch(u):
    r=requests.get(u,timeout=35,headers={'Accept':'application/vnd.github+json'})
    if r.status_code==404:return {'status':404,'url':u}
    r.raise_for_status()
    j=r.json()
    event={k:j.get(k) for k in ['number','created_at','merged_at','closed_at','merge_commit_sha','html_url','state']}
    event.update(status=200,url=u,github_etag=r.headers.get('ETag'))
    return event
def clip(s,n):
    return ' '.join(s.split()[:n])
def main():
    inputs=read(REPAIR/'inputs.json')
    cards={r['key']:r for r in read(PREV/'cards.json')}
    ranks=read(PREV/'blind_ranks.json')
    library={r['trace_key']:r['instance_id'] for r in csv.DictReader((PREV/'evaluation_library.csv').open(encoding='utf8'))}
    prereq=read(PREV/'blind_commit.json')
    for f in ['cards.json','blind_ranks.json']:
        assert digest(PREV/f)==prereq[f]
    src_lookup={}; urls=set()
    seen={}
    # Exclude target-side linkage and outcomes from prior-ID disambiguation.
    proj=pq.read_table(DATA/'SWEContextBench_Relationship.parquet',columns=['experience_instance_id','experience_pr_url']).to_pylist()
    for row in proj:
        prior=row['experience_instance_id']; v=row['experience_pr_url']
        if v:seen.setdefault(prior,set()).add(v.rstrip('/'))
    pool={r['instance_id']:r for r in pq.read_table(DATA/'SWEContextBench_Lite_Experience.parquet',columns=['repo','instance_id','base_commit']).to_pylist()}
    schema=pa.schema([('pull_number',pa.int64()),('issue_numbers',pa.list_(pa.string())),('instance_id',pa.string()),('repo',pa.string()),('base_commit',pa.string())])
    options=pjson.ParseOptions(explicit_schema=schema,unexpected_field_behavior='ignore',newlines_in_values=True)
    meta={}
    for row in inputs:
        iid=row['id']; repo=row['repo']
        m,=pjson.read_json(DATA/'case_metadata'/(iid+'.json'),parse_options=options).to_pylist()
        assert m['instance_id']==iid and m['repo']==repo and m['base_commit']==row['commit']
        meta[iid]=m
        urls.update(url(repo,'issues',i) for i in m['issue_numbers'])
        urls.add(url(repo,'pulls',m['pull_number']))
        for key in [row['source_key'],*ranks[row['ordinal']]['fusion'][:10]]:
            sid=library[key]
            info=pool[sid]
            if info['repo']!=repo:continue
            references=sorted(seen.get(sid,[]))
            if len(references)==1 and re.fullmatch(r'https://github\.com/'+re.escape(repo)+r'/pull/\d+',references[0],re.I):
                number=int(re.search(r'\d+$',references[0])[0])
                source='author.experience_pr_url'
            elif not references: 
                number=int(sid.rsplit('-',1)[1])
                source='candidate_id_and_merge_parent_verification'
            else:
                src_lookup[sid]={'status':'ambiguous_source_identity','references':references}
                continue
            u=url(repo,'pulls',number);urls.add(u)
            src_lookup[sid]={'number':number,'url':u,'canonical':source,'base_commit':info['base_commit']}
    with cf.ThreadPoolExecutor(max_workers=4) as e:cache=dict(zip(sorted(urls),e.map(fetch,sorted(urls))))
    # For unmapped public experiences, independently check base SHA against first merge parent.
    for sid,v in src_lookup.items():
        if v.get('canonical')!='candidate_id_and_merge_parent_verification': continue
        obj=cache[v['url']]
        if not obj.get('merge_commit_sha'): continue
        u=url(pool[sid]['repo'],'commits',obj['merge_commit_sha'])
        response=requests.get(u,params={'per_page':1},timeout=40,headers={'Accept':'application/vnd.github+json'})
        if response.status_code in (404,422):
            cache[u]={'url':u,'status':response.status_code,'parent_ids':[]}
            v['verified_parent']=False
            continue
        response.raise_for_status()
        jj=response.json()
        cache[u]={'sha':jj['sha'],'parent_ids':[a['sha'] for a in jj['parents']],'status':response.status_code,'html_url':jj['html_url'],'url':u}
        v['verified_parent']=bool(jj['parents'] and jj['parents'][0]['sha']==v['base_commit'])
    rows=[];audit=[]
    for row in inputs:
        iid=row['id'];repo=row['repo'];m=meta[iid]
        opens=[cache[url(repo,'issues',i)].get('created_at') for i in m['issue_numbers']]
        cutoff=min(opens,key=parse) if opens and all(opens) else None
        def inspect(key,rank):
            sid=library[key];b={'rank':rank,'source_key':key,'source_id':sid,'repo':pool[sid]['repo']}
            v=src_lookup.get(sid,{})
            if pool[sid]['repo']!=repo:return {**b,'status':'other_repo'}
            if 'url' not in v:return {**b,'status':'unknown_identity'}
            details=cache[v['url']]; merged=details.get('merged_at')
            b.update(source_pr=v['number'],source_merged_at=merged,source_reference=details.get('html_url'),
                     source_identity=v['canonical'],is_target_pr=(v['number']==m['pull_number']))
            if b['is_target_pr']:s='target_self'
            elif v['canonical'].startswith('candidate_id') and not v.get('verified_parent'):s='unverified_source_id'
            elif not cutoff or not merged:s='unknown_time'
            elif parse(merged)>=parse(cutoff):s='after_target_issue_open'
            else:s='eligible'
            return {**b,'status':s}
        top=[inspect(k,n) for n,k in enumerate(ranks[row['ordinal']]['fusion'][:10],1)]
        prior=inspect(row['source_key'],None)
        chosen=next((c for c in top if c['status']=='eligible'),None)
        original=library[row['source_key']]
        assert original==row['source_id']
        key=chosen['source_key'] if chosen else None
        card=cards[key] if key else None
        same=[k for k,x in meta.items() if x['repo']==repo and x['pull_number']==m['pull_number'] and x['base_commit']==m['base_commit']]
        tag={'id':iid,'repo':repo,'base_commit':m['base_commit'],'target_pr':m['pull_number'],'target_issues':m['issue_numbers'],'target_opened_at':cutoff,'same_outcome_keys':same}
        rows.append({**tag,'source_key':key,'source_id':chosen['source_id'] if chosen else None,'source_pr':chosen['source_pr'] if chosen else None,'source_merged_at':chosen['source_merged_at'] if chosen else None,'rank':chosen['rank'] if chosen else None,
                     'abstain':not bool(chosen), **{f:clip(card[f],n) if card else '' for f,n in [('symptom',175),('closure',90),('edits',40)]}})
        audit.append({**tag,'original_frozen_choice':prior,'top10':top})
    save('github_events.json',cache)
    save('eligibility.json',audit)
    save('selected.json',rows)
    save('freeze.json',{'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'policy':'Highest rank eligible among 10 frozen fusion candidates in same repo. Source merged before all associated target issue opens. Same PR excluded. Fail closed on unknown.','files':{n:digest(OUT/n) for n in ['build.py','selected.json','github_events.json','eligibility.json']},'previous_inputs':{n:digest(PREV/n) for n in ['cards.json','blind_ranks.json','evaluation_library.csv']},'official_target_metadata':{iid:digest(DATA/'case_metadata'/(iid+'.json')) for iid in meta},'official_inputs':{n:digest(DATA/n) for n in ['SWEContextBench_Lite_Experience.parquet','SWEContextBench_Relationship.parquet']}})
    for r in rows:
        print(r['id'],r['source_key'],r['source_id'],r['source_merged_at'],r['target_opened_at'],r['rank'])
if __name__=='__main__': main()

