"""Compare the paper's published timestamp with public PR and issue metadata of a fixed sample."""
import re,requests
from sources import BASE,fetch,h,load,save,digest,when

def metadata(repo,route,number):
    if number is None:return {'status':'no_reference'}
    url=f'https://api.github.com/repos/{repo}/{route}/{number}'
    reply=requests.get(url,timeout=15)
    result={'url':url,'status':reply.status_code}
    if reply.status_code==200:
        rec=reply.json();result.update(created_at=rec.get('created_at'),closed_at=rec.get('closed_at'),merged_at=rec.get('merged_at'))
    return result

def main():
    selected={r['issue'] for r in load(BASE/'decisions.json.gz') if r['cohort']=='chronological'}
    allrows=fetch('Related',['repo','instance_id','created_at'])
    edges=fetch('Relationship',['related_instance_id','related_pr_url','related_issue_url'])
    link={}
    for e in edges:link.setdefault(e['related_instance_id'],e)
    eligible=sorted((r for r in allrows if h(r['repo']+'#issue#'+r['instance_id']) in selected),key=lambda r:digest(r['instance_id'].encode()))
    seen=set();examples=[]
    for r in eligible:
        if r['repo'] in seen:continue
        seen.add(r['repo']);e=link[r['instance_id']]
        nums=[re.search(p,e[k] or '') for k,p in [('related_pr_url',r'/pull/(\d+)'),('related_issue_url',r'/issues/(\d+)')]]
        pr,issue=[metadata(r['repo'],route,m[1] if m else None) for route,m in zip(('pulls','issues'),nums)]
        target=when(r['created_at'])
        examples.append(dict(repo=r['repo'],source_target=r['instance_id'],published_created_at=r['created_at'],official_pr=pr,official_issue=issue,
                             matches_pr_creation=bool(pr.get('created_at')) and when(pr['created_at'])==target,
                             matches_issue_creation=bool(issue.get('created_at')) and when(issue['created_at'])==target))
        if len(examples)==4:break
    assert len(examples)==4
    save(BASE/'date_semantics.json',examples)
    print('Related.created_at equals linked PR created_at',sum(e['matches_pr_creation'] for e in examples),'or issue created_at',sum(e['matches_issue_creation'] for e in examples),'of',len(examples))
if __name__=='__main__':main()
