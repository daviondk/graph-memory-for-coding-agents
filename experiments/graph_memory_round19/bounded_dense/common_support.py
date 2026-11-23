"""Exact decomposition of absolute full-support differences by storage outcomes."""
from collections import defaultdict
from statistics import mean
from inputs import ROOT,TR,load,put,pilot
def allocate():
    put(ROOT/'analysis-plan.json',dict(note=pilot.sha(ROOT/'COMMON_SUPPORT_RU.md'),source=pilot.sha(ROOT/'common_support.py'),reader_plan=pilot.sha(ROOT/'reader-plan.json')))
def run():
    plan=load(ROOT/'analysis-plan.json');assert plan['source']==pilot.sha(ROOT/'common_support.py') and plan['reader_plan']==pilot.sha(ROOT/'reader-plan.json')
    rows=load(ROOT/'outcomes.json.gz');keys={(r['stage'],r['q'],r['writer'],r['reader']):r for r in rows}
    dev500={r['q'] for r in load(TR/'split.json.gz')['dev']};res={}
    for stage in ('test','dev','dev500','dev80'):
        src='test' if stage=='test' else 'dev';qs=sorted({r['q'] for r in rows if r['stage']==src and (stage not in ['dev500','dev80'] or (r['q'] in dev500)==(stage=='dev500'))});out={}
        for rd in ('dense','bm25','rrf60'):
            cats=defaultdict(list)
            for q in qs:
                a=keys[src,q,'full',rd];b=keys[src,q,'output_head',rd]
                cats[f"{int(a['write_fs'])}{int(b['write_fs'])}"].append((a,b))
            cs={}
            for k in ['11','10','01','00']:
                rr=cats[k];cs[k]=dict(n=len(rr),full_reader_hits=int(sum(a['full_support'] for a,b in rr)),output_head_reader_hits=int(sum(b['full_support'] for a,b in rr)),
                    wins=sum(a['full_support']>b['full_support'] for a,b in rr),losses=sum(a['full_support']<b['full_support'] for a,b in rr))
            out[rd]=dict(n=len(qs),cells=cs,full_hits=sum(d['full_reader_hits'] for d in cs.values()),head_hits=sum(d['output_head_reader_hits'] for d in cs.values()))
        res[stage]=out
    put(ROOT/'common-support.json',res)
if __name__=='__main__':
    import sys
    {'plan':allocate,'score':run}[sys.argv[1]]()
