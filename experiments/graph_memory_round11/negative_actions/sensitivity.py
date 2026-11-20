"""Post-hoc checks of PR attribution and equal-budget hash placement after oracle eligibility."""
from collections import Counter,defaultdict
from fractions import Fraction
from math import comb
from harvest import D,get,save
from replay import grep_run
from git_pairs import local,git
def main():
    rows=get(D/"checked_rows.json");valid=[r for r in rows if r['old_oracle'].get('hit') is False and r['new_oracle']['valid']]
    direct={t:{'n':len(s),'change':sum(r['new_oracle']['hit'] for r in s),'exact_reruns':sum(r['exact'] for r in s),'scope_reruns':sum(r['scope'] for r in s)} for t in ('strict','weak') if (s:=[r for r in valid if r['tier']==t and r['parent_match']])}
    adhoc=[]
    for r in valid:
        if not r['new_oracle']['hit']:continue
        repo=local(r['repo']);p=r['merge_parents'][0]
        if p!=r['old_sha']:
            git(repo,"fetch","--no-tags","--depth=1","--filter=blob:none","origin",p)
        result=grep_run(r['repo'],p,r['key'])
        adhoc.append({'iid':r['iid'],'pr':r['pr'],'base':r['old_sha'],'merge':r['new_sha'],'first_parent':p,'was_present_in_first_parent':result.get('hit'),'present_after_merge':r['new_oracle']['hit'],'functional_attribute':'literal_presence_only'})
    weak=[r for r in valid if r['tier']=='weak']
    dist={0:Fraction(1)};ns=[]
    for panel in sorted({r['panel'] for r in weak}):
        samples=[r for r in weak if r['panel']==panel];n=len(samples);k=sum(r['use_next_three'] for r in samples);g=sum(r['new_oracle']['hit'] for r in samples)
        ns.append(dict(panel=panel,n=n,keep=k,changed=g))
        sub={j:Fraction(comb(g,j)*comb(n-g,k-j),comb(n,k)) for j in range(min(g,k)+1) if 0<=k-j<=n-g}
        tmp=defaultdict(Fraction)
        for i,pi in dist.items():
            for j,pj in sub.items():tmp[i+j]+=pi*pj
        dist=tmp
    saved=sum(d['keep'] for d in ns);tot=len(weak)
    distribution={str(tot-saved+j):float(p) for j,p in sorted(dist.items())}
    out={'direct_parent_subset':direct,'first_parent_check':adhoc,'equal_budget_after_eligibility':{'blocks':ns,'stored':saved,'random_reread_distribution':distribution,'expected_rereads':sum(float(k)*p for k,p in distribution.items()),'use_rereads_observed':sum(not r['use_next_three'] or r['exact'] for r in weak)}}
    save(D/'sensitivity.json',out);print(out)
if __name__=="__main__":main()
