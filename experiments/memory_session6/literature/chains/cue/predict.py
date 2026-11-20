"""Freeze one causal pointer decision for each policy before grading."""
from collections import Counter
from math import log,fsum
import sys
from common import HERE,WRITE,digest,load,save
sys.path.insert(0,str(WRITE))
from retain import update

METHODS=('recency','path','latest8','stable8','uniform8','full_latest')
CUES=METHODS[2:]


def online_records(history):
    cache={};records={};churn=0;prior_stable_scanned=0
    writes=Counter()
    for tick,s in enumerate(history):
        files=s['files'];terms=s['terms'];rank=sorted(terms,key=lambda w:(-terms[w],w))
        updated=update(cache,{p:f['folder'] for p,f in files.items()},tick,'confirmation',8)
        churn+=len(updated.keys()-cache.keys())
        nxt={}
        for p in updated:
            if p not in files:
                nxt[p]=records[p]
                continue
            prev=records[p]['stable8'] if p in records else []
            prior_stable_scanned+=len(prev)
            shared=sorted((w for w in prev if w in terms),key=lambda w:(-terms[w],w))[:4]
            promoted=set(shared)
            new=dict(path=files[p]['words'],latest8=rank[:8],stable8=(shared+[w for w in rank if w not in promoted])[:8],
                     uniform8=sorted(terms)[:8],full_latest=sorted(terms))
            assert len(new['stable8'])==len(new['latest8'])==len(new['uniform8'])
            for m in CUES:
                # Count word identities newly written relative to the same resident record.
                writes[m]+=len(set(new[m])-set(records[p][m] if p in records else ()))
            nxt[p]=new
        cache=updated;records=nxt
    assert cache and set(cache)==set(records)
    return cache,records,churn,prior_stable_scanned,dict(writes)


def lexical_scores(records,query,kind):
    n=len(records)
    freq=Counter(w for r in records.values() for w in set(r[kind]))
    return {p:fsum(log((n+1)/(freq[w]+1)) for w in sorted(query.intersection(r[kind]))) for p,r in records.items()}


def predict(r):
    cache,records,churn,scanned,writes=online_records(r['history'])
    assert sorted(cache)==r['expected_cache']
    query=set(r['query'])
    path_scores=lexical_scores(records,query,'path')
    methods={}
    for method in METHODS:
        cue=lexical_scores(records,query,method) if method in CUES else {}
        values={p:(0 if method=='recency' else path_scores[p])+cue.get(p,0) for p in records}
        order=sorted(values,key=lambda p:(-values[p],-cache[p][0],p))
        p=order[0]
        words=sum(len(x[method]) for x in records.values()) if method in CUES else 0
        methods[method]=dict(choice=p,top_score=values[p],top_ties=sum(v==values[p] for v in values.values()),
                             cue_ids=words,words_written=writes.get(method,0))
    return dict(repo=r['repo'],issue=r['issue'],sequence=r['sequence'],prefix=r['prefix'],candidates=sorted(cache),
                methods=methods,admissions=churn,stable_prior_word_ids_scanned=scanned,
                resident_path_terms=sum(len(x['path']) for x in records.values()),issue_word_ids=len(query),
                differing_stable_vs_latest_records=sum(set(x['stable8'])!=set(x['latest8']) for x in records.values()))


def main():
    rows=load(HERE/'features.json.gz');s=load(HERE/'source.json')
    assert digest((HERE/'features.json.gz').read_bytes())==s['features_sha256'] and len(rows)==s['selected_targets']==374
    out=[predict(r) for r in rows]
    assert len({(r['repo'],r['issue']) for r in out})==374
    save(HERE/'decisions.json.gz',out)
    names=['PROTOCOL.md','IMPLEMENTATION.md','project_cues.py','common.py','predict.py','features.json.gz','source.json','decisions.json.gz']
    save(HERE/'decision_lock.json',dict(n=374,methods=list(METHODS),sha256={n:digest((HERE/n).read_bytes()) for n in names},
             historical_writer_sha256=digest((WRITE/'retain.py').read_bytes()),upstream_roster_sha256=s['write_roster_sha256']))
    print('Frozen one pointer for all',len(out),'prefixes and',len(METHODS),'policies.')

if __name__=='__main__':main()
