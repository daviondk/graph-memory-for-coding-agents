"""Paired summaries over the frozen source attempts. Use issue clusters for the new cohort."""
from collections import Counter,defaultdict
from statistics import median
import numpy as np
from source import D,read,save,digest

def summarize(indices,panel,outcomes,known_templates):
    rows=[panel[i] for i in indices];scored=[(panel[i],outcomes[i]) for i in indices if i in outcomes and outcomes[i].get('full_calls')]
    actual=[(r,o) for r,o in scored if o['span'] is not None]
    read_subset=[(r,o) for r,o in scored if o['bytes_read']]
    counters=Counter()
    for r,o in scored:counters[(o['status'])]+=1
    baseline=sum(o['full_read'] for _,o in scored);local=sum(o['bytes_read'] for _,o in scored);match_full=sum(o['full_read'] for _,o in read_subset)
    issue=defaultdict(lambda:[0,0])
    for r,o in read_subset:issue[r[4]][0]+=o['bytes_read'];issue[r[4]][1]+=o['full_read']
    ci=None
    if len(issue)>=2:
        vectors=np.asarray([issue[k] for k in sorted(issue)]);rng=np.random.default_rng(414011)
        idx=rng.integers(0,len(vectors),size=(10000,len(vectors)));sums=vectors[idx].sum(axis=1)
        ci=np.quantile(sums[:,0]/sums[:,1],[.025,.975]).tolist()
    return dict(views=len(indices),runs=len({r[0] for r in rows}),issues=len({r[4] for r in rows}),with_receipt=sum(r[2] is not None for r in rows),
        statuses=dict(Counter(r[8] for r in rows)),scored=len(scored),scored_issues=len({r[4] for r,_ in scored}),score_receipts=len({(r[0],r[2]) for r,_ in scored}),
        score_revisions=len({o['revision'] for _,o in scored}),score_tail_patterns=len({r[9] for r,_ in scored}),scored_new_tail=sum(r[9] not in known_templates for r,_ in scored),
        accepted_new_tail=sum(r[9] not in known_templates for r,_ in actual),accepted_new_patterns=len({r[9] for r,_ in actual if r[9] not in known_templates}),
        score_states=dict(counters),accepted=len(actual),accepted_full_unique=sum(o['placements']==1 for _,o in actual),accepted_globally_ambiguous=sum(o['placements']>1 for _,o in actual),
        full_scan_unique=sum(o['placements']==1 for _,o in scored),full_scan_multiple=sum(o['placements']>1 for _,o in scored),full_scan_no_match=sum(o['placements']==0 for _,o in scored),
        full_endpoint_resolved=sum(o['valid_end_matches']==1 for _,o in scored),endpoint_not_global_unique=sum(o['valid_end_matches']==1 and o['placements']>1 for _,o in scored),
        returned_lines=sum(o['tail_lines'] for _,o in actual),visible_tail_lines=sum(o['tail_lines'] for _,o in scored),
        full_unique_lines=sum(o['tail_lines'] for _,o in scored if o['placements']==1),logical_calls=sum(o['read_calls'] for _,o in scored),
        full_logical_calls=len(scored),open_eof_reads=len(read_subset),read_bytes=local,full_bytes=baseline,full_bytes_on_same_attempts=match_full,
        read_fraction_same=local/match_full if match_full else None,read_fraction_ci=ci,
        median_probe=median([o['bytes_read'] for _,o in read_subset]) if read_subset else None,median_full_on_same=median([o['full_read'] for _,o in read_subset]) if read_subset else None,
        eof_read_issues=len(issue),guard_recovered_tail_lines=0,original_origin_proven=0)

def main():
    assert digest(D/'outcomes.json.gz')==read(D/'score-seal.json')['outcomes']
    panel=read(D/'panel.json.gz');outcomes={int(k):v for k,v in read(D/'outcomes.json.gz').items()}
    known_templates={r[9] for r in panel if r[12]=='known' and r[9]}
    levels={'known':lambda r:r[12]=='known','novel':lambda r:r[12]=='novel','novel_clean':lambda r:r[12:14]==['novel','clean'],
        'novel_opaque':lambda r:r[12:14]==['novel','opaque'],'novel_unseen_tail':lambda r:r[12]=='novel' and r[9] and r[9] not in known_templates,
        'all_r37_views':lambda r:len(r)==15 and r[11],'all_parsed_views':lambda r:len(r)==15 and r[8]!='unparseable',
        'all_additional':lambda r:len(r)==15 and r[12]=='extra','outside_r37_parser':lambda r:len(r)==15 and not r[11]}
    results={k:summarize([i for i,r in enumerate(panel) if keep(r)],panel,outcomes,known_templates) for k,keep in levels.items()}
    save('results.json',dict(groups=results,score_seal=digest(D/'score-seal.json'),bootstrap=dict(samples=10000,seed=414011,cluster='issue')))
    for g in ('known','novel','novel_clean','novel_opaque','all_parsed_views','all_r37_views'):
        r=results[g];print(g,{k:r[k] for k in ('views','scored','accepted','accepted_full_unique','accepted_new_tail','accepted_new_patterns','full_scan_unique','read_bytes','full_bytes_on_same_attempts','read_fraction_ci')})
if __name__=='__main__':main()
