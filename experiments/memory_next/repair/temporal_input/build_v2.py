"""Expand prior identity verification to authoritative PR base SHA and creation time."""
from pathlib import Path
import json, datetime
import pyarrow.parquet as pq
import requests
from build import OUT,DATA,PREV,clip,digest,save,read,parse,url

def main():
    existing=read(OUT/'freeze.json')
    for f,h in existing['files'].items():assert digest(OUT/f)==h
    audit=read(OUT/'eligibility.json')
    base=read(OUT/'selected.json')
    official={r['instance_id']:r for r in pq.read_table(DATA/'SWEContextBench_Lite_Experience.parquet',
              columns=['repo','instance_id','base_commit','created_at']).to_pylist()}
    cards={r['key']:r for r in read(PREV/'cards.json')}
    unknown=set(c['source_id'] for row in audit for c in row['top10'] if c['status']=='unverified_source_id')
    evidence={}
    for sid in sorted(unknown):
        orig=official[sid]
        number=int(sid.rsplit('-',1)[1])
        u=url(orig['repo'],'pulls',number)
        response=requests.get(u,timeout=35);response.raise_for_status();o=response.json()
        ev={'api':u,'html_url':o['html_url'],'official_repo':orig['repo'],'github_repo':o['base']['repo']['full_name'],
            'pr_number':o['number'],'official_created_at':str(orig['created_at']),'github_created_at':o['created_at'],
            'official_base':orig['base_commit'],'github_base':o['base']['sha'],'merged_at':o.get('merged_at')}
        ev['confirmed']=bool(o['number']==number and ev['official_repo'].lower()==ev['github_repo'].lower() and ev['official_base']==ev['github_base'] and parse(ev['official_created_at'])==parse(ev['github_created_at']))
        evidence[sid]=ev
    for meta,r in zip(audit,base):
        for c in [*meta['top10'],meta['original_frozen_choice']]:
            e=evidence.get(c['source_id'],{})
            if c['status']=='unverified_source_id' and e.get('confirmed'):
                if int(c['source_pr'])==int(meta['target_pr']):c['status']='target_self'
                elif not (meta['target_opened_at'] and e['merged_at']): c['status']='unknown_time'
                elif parse(e['merged_at'])>=parse(meta['target_opened_at']): c['status']='after_target_issue_open'
                else:c['status']='eligible'
                c['source_identity']='GitHub PR repo, number, full base SHA and opened_at equal official source row'
        chosen=next((x for x in meta['top10'] if x['status']=='eligible'),None)
        if chosen:
            card=cards[chosen['source_key']]
            r.update({k:chosen[k] for k in ['source_key','source_id','source_pr','source_merged_at','rank']})
            r.update(abstain=False, **{f:clip(card[f],n) for f,n in [('symptom',175),('closure',90),('edits',40)]})
        else:assert r['abstain']
    save('source_identity_v2.json',evidence)
    save('eligibility_v2.json',audit)
    save('selected_v2.json',base)
    save('freeze_v2.json',{'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'original_freeze_sha256':digest(OUT/'freeze.json'),'files':{f:digest(OUT/f) for f in ['build_v2.py','source_identity_v2.json','eligibility_v2.json','selected_v2.json']}})
    for r in base:print(r['id'],r['source_key'],r['source_id'],r['rank'])
if __name__=='__main__':main()

