"""Project PR creation timestamps of the exact locked source rows for strict confirmation."""
from collections import defaultdict
from sources import fetch,dedup,h,load,save,BASE,when

def main():
    full=fetch('Related',['repo','instance_id','created_at','patch','problem_statement'])
    chosen={r['issue'] for r in load(BASE/'features.json.gz') if r['cohort'] in ('chronological','linked')}
    first=dedup(full)
    dates={h(repo+'#issue#'+sid):r['created_at'] for (repo,sid),r in first.items() if h(repo+'#issue#'+sid) in chosen}
    assert set(dates)==chosen
    groups=defaultdict(list)
    for r in full:groups[r['repo'],r['instance_id']].append(r)
    repeats=[v for v in groups.values() if len(v)>1]
    facts=dict(duplicated_ids=len(repeats),different_statement=sum(len({r['problem_statement'] for r in v})>1 for v in repeats),
               different_patch=sum(len({r['patch'] for r in v})>1 for v in repeats),
               different_timestamp=sum(len({r['created_at'] for r in v})>1 for v in repeats),frozen_targets=len(chosen))
    save(BASE/'strict_target_dates.json',dates);save(BASE/'related_duplicate_audit.json',facts)
    print(facts)

if __name__=='__main__':main()
