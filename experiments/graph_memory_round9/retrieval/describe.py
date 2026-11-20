"""Summarize true additions and paired costs, used for the report."""
from collections import Counter
from source import ROOT,load_json,write_json
def main():
    d=load_json(ROOT/'results.json');s=load_json(ROOT/'stop_results.json')
    ids=list(d['details']);means=d['means']
    methods=list(means);totals={}
    for m in methods:
        z=[v['methods'][m] for v in d['details'].values()]
        totals[m]={k:sum(v[k] for v in z) for k in ['seed_reads','extra_reads','new_correct','removed_correct','returned_correct','acc5','acc10','acc15']}
    strat={}
    for b in sorted({v['band'] for v in d['details'].values()}):
        group=[t for t in ids if d['details'][t]['band']==b]
        strat[b]={'n':len(group),'n_functions':sum(d['details'][t]['n_corpus'] for t in group),'acc10':{m:sum(d['details'][t]['methods'][m]['acc10'] for t in group) for m in methods}}
    oracle=s['oracle_after_seal']
    out=dict(method_totals=totals,strata=strat,all_true=sum(v['n_gold'] for v in d['details'].values()),gold_outside_dense10=sum(v['gold_outside_top10'] for v in oracle.values()),reachable_outside=sum(len(v['reachable_gold_outsiders']) for v in oracle.values()),n_issues_miss=sum(v['gold_outside_top10']>0 for v in oracle.values()),n_issues_reachable=sum(bool(v['reachable_gold_outsiders']) for v in oracle.values()),edges=sum(v['stored_edges'] for v in d['details'].values()),bytes=sum(v['edge_bytes'] for v in d['details'].values()),seed_wordpieces=sum(v['seed_wordpieces'] for v in d['details'].values()),differences_vs_dense={m:[(t,d['details'][t]['methods'][m]['acc10']-d['details'][t]['methods']['dense']['acc10']) for t in ids if d['details'][t]['methods'][m]['acc10']!=d['details'][t]['methods']['dense']['acc10']] for m in methods})
    write_json(ROOT/'descriptive.json',out)
    print('primary',d['contrasts']['corroborated-dense']['acc10'])
    print('cost',s['contrasts']['early3-fixed6']['seed_reads'],'quality',s['contrasts']['early3-fixed6']['acc10'])
    print('oracle',out['gold_outside_dense10'],out['reachable_outside'])
    print('discordant',out['differences_vs_dense'])
if __name__=='__main__':main()
