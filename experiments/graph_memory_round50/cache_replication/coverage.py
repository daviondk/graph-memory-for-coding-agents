"""Summarize panel coverage and composition without textual source excerpts."""
from lineage import *
def main():
    old=rd(FROZEN/'inputs.json.gz');test=rd(D/'inputs.json.gz');r=rd(D/'results.json');old_eligible=rd(W/'graph_memory_round34/external_transfer/features.json.gz')
    orig={z['state_id']:z for z in map(json.loads,gzip.open(PUB/'cal500/items.jsonl.gz','rt',encoding='utf8'))}
    issues={orig[q]['instance_id'] for q in old};repos={z['repo'] for z in old.values()}
    remainder=[z for q,z in orig.items() if q in old_eligible and q not in old]
    pairs=0
    for z in remainder:
        e=z['trajectory_prefix']
        for a in remainder:
            short=a['trajectory_prefix']
            if a['instance_id']==z['instance_id'] and a['repo']==z['repo'] and a['base_commit']==z['base_commit'] and len(short)<len(e) and short==e[:len(short)]:pairs+=1
    splits={}
    for mode,rows in [('R48',old),('R49',old),('Test500',test)]:
        states=[z for z in rows.values() if z['panel']==mode];n=sum(len(z['docs']) for z in states)
        splits[mode]=dict(states=len(states),unique_documents_per_state_sum=n,python=sum(a[5] for z in states for a in z['docs'].values()),
            observed=sum(a[6] for z in states for a in z['docs'].values()))
    dump('coverage.json',dict(cal_total=500,old_eligible=len(old_eligible),old_used=len(old),safe_left=len(remainder),
        safe_left_issues=len({z['instance_id'] for z in remainder}),safe_left_new_repos=sum(z['repo'] not in repos for z in remainder),
        safe_left_new_issues=sum(z['instance_id'] not in issues for z in remainder),safe_left_edges=pairs,composition=splits))
if __name__=='__main__':main()

