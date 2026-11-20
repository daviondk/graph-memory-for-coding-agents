"""Data-only source adapter. Public issue text and already-finished patch headers are never executed."""
from collections import Counter,defaultdict
from datetime import datetime,timezone
import io
from pathlib import Path,PurePosixPath
import re
import sys
import pyarrow.parquet as pq
import requests
BASE=Path(__file__).resolve().parent
CUE=BASE.parent/'cue'
sys.path.insert(0,str(CUE))
from common import digest,ident,load,save
from project_cues import DENY,EXCLUDE,HEADER,EXPECTED,URL,h,bag
REV='12c65bd15e2559bc808065565e941ee7bbbd008f'
HF=f'https://huggingface.co/datasets/jiayuanz3/SWEContextBench/resolve/{REV}/data/SWEContextBench_'
SHA={'Relationship':'f59b1a0fd021c6608bd185f15113cbbd26f804c20494da6d4827adb9ea70edb5',
     'Experience':'e10d452123257fabc604e77985e34184ad7504788106ee3ac3e7e8f621303610',
     'Related':'394ce86dbf8e5b7471264625ad4879d70c676a5b43dd16e4d7416592547c8892'}


def fetch(which,cols):
    url=URL if which=='Chain' else HF+which+'.parquet'
    rr=requests.get(url,timeout=90);rr.raise_for_status()
    assert digest(rr.content)==(EXPECTED if which=='Chain' else SHA[which])
    return pq.ParquetFile(io.BytesIO(rr.content)).read(columns=cols).to_pylist()


def aliases(repo,sid,text,pr=None):
    repo=repo.casefold();sid=sid.casefold()
    keys={'id':ident(repo+'#id#'+sid),'text':ident('issue-text#'+' '.join(text.casefold().split()))}
    if not text.strip():del keys['text']
    m=(re.search(r'/pull/(\d+)(?:/|$)',pr or '') or re.search(r'[-#](\d+)$',sid))
    if m:keys['pr']=ident(repo+'#pr#'+m[1])
    return keys


def collisions(keys,prev):
    return sorted(k for k,v in keys.items() if v in prev)


def files(repo,patch):
    allowed={}
    for p in HEADER.findall(patch or ''):
        raw=PurePosixPath(p);parts=raw.parts;name=parts[-1].casefold()
        if (not name.endswith('.py') or name.startswith('test_') or name.endswith('_test.py') or name=='conftest.py'
            or any(c.casefold() in EXCLUDE for c in parts) or DENY.search(p.replace('_',' '))):
            continue
        allowed[h(repo+'#'+p)]={'folder':h(repo+'#dir#'+'/'.join(parts[:-1])),
                                'words':sorted(bag(' '.join((*parts[:-1],raw.stem))))}
    return allowed


def when(v):
    try:
        x=datetime.fromisoformat((v or '').replace('Z','+00:00'))
        return x if x.tzinfo is not None else x.replace(tzinfo=timezone.utc)
    except ValueError:return None


def dedup(rows):
    out={}
    for r in rows:out.setdefault((r['repo'],r['instance_id']),r)
    return out


def main():
    log=Counter()
    mainset=load(CUE/'features.json.gz')
    targets_by_seq=defaultdict(list)
    for r in mainset:targets_by_seq[r['sequence']].append(r)
    chains=fetch('Chain',['continuous_id','repo','bug_fixes.list.element.swebench_instance_id','bug_fixes.list.element.problem_statement','bug_fixes.list.element.patch'])
    main_ids=set();main_hist=set();main_repos=set()
    for row in chains:
        seq=h(row['continuous_id']);repo=row['repo']
        for spec in targets_by_seq.get(seq,[]):
            idx=spec['prefix'];target=row['bug_fixes'][idx];sid=target['swebench_instance_id']
            assert spec['issue']==h(repo+'#issue#'+sid)
            main_ids.update(aliases(repo,sid,target['problem_statement'] or '').values())
            for past in row['bug_fixes'][:idx]:
                main_hist.update(aliases(repo,past['swebench_instance_id'],past['problem_statement'] or '').values())
            main_repos.add(repo.casefold())
            log['verified_main_targets']+=1
    assert log['verified_main_targets']==374
    related=fetch('Related',['repo','instance_id','problem_statement','created_at'])
    experiences=fetch('Experience',['repo','instance_id','problem_statement','created_at','patch'])
    links=fetch('Relationship',['related_instance_id','experience_instance_id','related_pr_url','experience_pr_url'])
    log.update(unique_related=len(dedup(related)),related_rows=len(related),experience_rows=len(experiences),unique_experience=len(dedup(experiences)),direct_edges=len(links))
    ri=dedup(related);ei=dedup(experiences);by_repo=defaultdict(list);rel=defaultdict(set);rpr={}
    for edge in links:
        rel[edge['related_instance_id']].add(edge['experience_instance_id']);rpr.setdefault(edge['related_instance_id'],edge['related_pr_url'])
    for (repo,sid),r in ei.items():
        stamp=when(r['created_at'])
        if not stamp:log['experience_invalid_date']+=1;continue
        txt=r['problem_statement'] or ''
        if DENY.search(txt):log['experience_safety_excluded']+=1;continue
        by_repo[repo].append((stamp,sid,r))
    for vals in by_repo.values():vals.sort(key=lambda x:(x[0],ident(x[1])))
    projected=[];used_sources={};ex_targets=set()
    def materialize(repo,k,r):
        key=(repo,k)
        if key not in used_sources:
            used_sources[key]={'issue':h(repo+'#issue#'+k),'terms':bag(r['problem_statement'] or ''),'files':files(repo,r['patch'])}
        return used_sources[key]
    for (repo,sid),r in sorted(ri.items()):
        stamp=when(r['created_at']);txt=r['problem_statement'] or '';alias=aliases(repo,sid,txt,rpr.get(sid))
        if not stamp:log['related_invalid_date']+=1;continue
        if DENY.search(txt):log['related_safety_excluded']+=1;continue
        collision=collisions(alias,main_ids)
        if collision:
            log['related_overlap_with_main_targets']+=1
            for k in collision:log['related_overlap_via_'+k]+=1
            continue
        allprior=[(s,i,x) for s,i,x in by_repo[repo] if s<stamp and i!=sid]
        # Duplicated textual/PR identity of the target cannot be imported as its own experience.
        allprior=[v for v in allprior if not collisions(aliases(repo,v[1],v[2]['problem_statement'] or ''),set(alias.values()))]
        pools={'chronological':allprior[-8:],'linked':[v for v in allprior if v[1] in rel[sid]]}
        for label,pool in pools.items():
            if not pool:log[label+'_no_prior']+=1;continue
            hist=[materialize(repo,k,x) for _,k,x in pool]
            if not any(old['files'] for old in hist):
                log[label+'_empty_cache']+=1;continue
            ex_targets.update(alias.values())
            projected.append(dict(cohort=label,repo=ident('repo#'+repo),issue=h(repo+'#issue#'+sid),sequence=ident('official-'+label+'#'+sid),prefix=len(hist),
                         history=hist,query=sorted(bag(txt)),aliases=alias,shared_main_repo=repo.casefold() in main_repos,
                         previously_in_main_history=bool(collisions(alias,main_hist))))
            log[label+'_frozen']+=1
    choices={}
    for row in chains:
        if len(row['bug_fixes'])<2:continue
        repo=row['repo'];seq=h(row['continuous_id']);old,t=row['bug_fixes'][:2]
        target_id=t['swebench_instance_id'];old_id=old['swebench_instance_id'];text=t['problem_statement'] or ''
        if old_id==target_id or DENY.search(text) or DENY.search(old['problem_statement'] or ''):continue
        alias=aliases(repo,target_id,text)
        if collisions(alias,main_ids):log['internal_positions_overlap_main']+=1;continue
        if collisions(alias,ex_targets):log['internal_positions_overlap_external']+=1;continue
        source=files(repo,old['patch'])
        if not source:continue
        issue=h(repo+'#issue#'+target_id);key=(repo,issue)
        rank=digest((seq+'/1').encode())
        if key in choices and rank>=choices[key][0]:continue
        choices[key]=(rank,dict(cohort='second',repo=ident('repo#'+repo),issue=issue,sequence=seq,prefix=1,
            history=[dict(issue=h(repo+'#issue#'+old_id),terms=bag(old['problem_statement'] or ''),files=source)],query=sorted(bag(text)),aliases=alias,
            shared_main_repo=repo.casefold() in main_repos,previously_in_main_history=bool(collisions(alias,main_hist))))
    projected.extend(v[1] for v in choices.values());log['second_frozen']=len(choices)
    for r in mainset:
        projected.append(dict(cohort='original',repo=r['repo'],issue=r['issue'],sequence=r['sequence'],prefix=r['prefix'],history=r['history'],query=r['query'],aliases={},shared_main_repo=True,previously_in_main_history=None))
    projected.sort(key=lambda r:(r['cohort'],r['repo'],r['issue']))
    assert len({(r['cohort'],r['repo'],r['issue']) for r in projected})==len(projected)
    save(BASE/'features.json.gz',projected)
    save(BASE/'sources.json',dict(chain_url=URL,chain_sha256=EXPECTED,official_prefix=HF,official_sha256=SHA,revision=REV,
        counts=dict(log),source_features_sha256=digest((BASE/'features.json.gz').read_bytes())))
    print('Eligibility before labels',dict(sorted(log.items())))

if __name__=='__main__':main()

