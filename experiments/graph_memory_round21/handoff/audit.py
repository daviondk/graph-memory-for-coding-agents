"""Independent reconstruction of candidate source provenance, split, observable inputs, and scoring."""
import ast
import csv
import gzip
import hashlib
import json
import sqlite3
from collections import Counter,defaultdict
from pathlib import Path
import numpy as np

from pointer_predict import Link,run
from predict import descriptors,nominate,pack

ROOT=Path(__file__).resolve().parent
CACHE=Path('D:/CodexResearch/x20-wikicontradict')

def digest(b): return hashlib.sha256(b).hexdigest()
def address(text): return digest(text.strip().encode())[:16]
def load(p): return json.loads(p.read_text(encoding='utf8'))


def main():
    inputs=load(ROOT/'input-lock.json')
    assert digest((CACHE/'wiki.csv').read_bytes())==inputs['corpus']
    rows=list(csv.DictReader((CACHE/'wiki.csv').open(encoding='utf-8-sig',newline='')))
    gold=load(CACHE/'gold.json')
    packets=load(CACHE/'packets.json')
    by_id={r['question_ID']:r for r in rows}
    labels={q['case']:q for q in gold}
    texts=defaultdict(set)
    for r in rows:
        for col in ('context1','context2'):
            texts[address(r[col])].add(r['WikipediaArticleTitle'].strip().casefold())
    count=0; local_best=Counter(); article_counts=Counter()
    eligible=[]
    for p in packets:
        r=by_id[p['case']]
        answer=labels[p['case']]
        truth=[address(r['context1']),address(r['context2'])]
        article=r['WikipediaArticleTitle'].strip().casefold()
        assert truth==answer['gold']
        saw=[]
        for i,group in enumerate(p['workers']):
            hashes=[c['id'] for c in group]
            assert len(set(hashes))==6 and truth[i] in hashes
            assert all(set(c)=={'id','text','bm','cos','sketch'} for c in group)
            assert all(c['id']==address(c['text']) for c in group)
            negative_ids=[h for h in hashes if h!=truth[i]]
            assert all(article not in texts[h] for h in negative_ids)
            saw.extend(negative_ids)
        assert len(set(saw))==10
        if answer['different'] and len(set(truth))==2:
            eligible.append(p['case'])
            article_counts[article]+=1
            rank=[max(enumerate(g),key=lambda x:(x[1]['cos'],-x[0]))[1]['id'] for g in p['workers']]
            local_best['both_top1']+=int(rank==truth)
        # At fixed worker packets and method, changing the case label never changes real nomination.
        sigs=descriptors(p['workers'])
        assert nominate(sigs,'paired',p['case'])==nominate(sigs,'paired','dummy')
        count+=1
    banned={'gold','answer1','answer2','WikipediaArticleTitle','contradictType','samepassage','question_ID'}
    for name in ['predict.py','pointer_predict.py']:
        tree=ast.parse((ROOT/name).read_text(encoding='utf8'))
        used={node.value for node in ast.walk(tree) if isinstance(node,ast.Constant) and isinstance(node.value,str)}
        assert not (used & banned)
    refs=load(CACHE/'wiki-workers.json')
    assert all(set(v)=={'case','workers'} and all(all(len(h)==16 and isinstance(int(h,16),int) for h in group) for group in v['workers']) for v in refs)
    db=sqlite3.connect((CACHE/'wiki-refs.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
    assert [row[1] for row in db.execute('pragma table_info(evidence)')]==['id','n','sketch','body']
    link=Link()
    for r in refs:
        for method in ('paired','length_e5'):
            p=run(r['case'],r['workers'],db,link,method,1536,False)
            q=run('dummy',r['workers'],db,link,method,1536,False)
            assert p==q
    link.close(); db.close()
    with gzip.open(ROOT/'forecasts.jsonl.gz','rt') as f:
        pred={(r['case'],r['method']):r for r in map(json.loads,f) if r['budget']==1536 and r['limit']=='fill' and r['case'] in eligible}
    strata=defaultdict(list); family=defaultdict(list)
    def hit(case,method,target):
        return int(all(h in group for h,group in zip(target,pred[(case,method)]['ids'])))
    mismatch=Counter()
    for i,k in enumerate(eligible):
        a=labels[k]
        diff=hit(k,'paired',a['gold'])-hit(k,'dense',a['gold'])
        strata[a['article']].append(diff)
        family[tuple(sorted(a['gold']))].append(diff)
        alternative=next(t for t in eligible[i+1:]+eligible[:i+1] if labels[t]['article']!=a['article'])
        for m in ('paired','dense'): mismatch[m]+=hit(k,m,labels[alternative]['gold'])
    out=dict(source_rows_checked=count,primary_questions=len(eligible),article_count=len(strata),unique_pairs=len(family),largest_article=max(article_counts.values()),both_gold_are_local_e5_top1=local_best['both_top1'],balanced_article_delta_pp=float(100*np.mean([np.mean(d) for d in strata.values()])),balanced_unique_pair_delta_pp=float(100*np.mean([np.mean(d) for d in family.values()])),evaluation_with_wrong_article_gold=dict(mismatch),renamed_case_replay_ordinary_protocols=2*len(refs),checks='Source labels used by evaluator and scenario builder to guarantee one gold endpoint per worker and exclude same-topic distractors. Selector sees no roles/titles/gold. This harness positively selects topical separation; case-name invariance holds for tested non-sham pointer policies. Actual pre-fetched candidate scenarios are not independent retrieval or actual agent runs.')
    (ROOT/'provenance-audit.json').write_text(json.dumps(out,sort_keys=True,indent=2)+'\n')
    print(json.dumps(out,ensure_ascii=False))
if __name__=='__main__': main()

