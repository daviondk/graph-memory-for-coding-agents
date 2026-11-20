"""Audit seals, issue identities, total rank permutations and metric invariants."""
import hashlib
import json
from pathlib import Path
from acquire import ROOT
def load(name):return json.loads((ROOT/name).read_text(encoding='utf-8'))
panels={'swe_rerank':('seal.json','predictions','results.json'),'swe_pool':('pool_seal.json','pool_predictions','pool_results.json'),'loc_full':('loc_seal.json','loc_predictions','loc_results.json'),'swe_degree':('degree_seal.json','degree_predictions','degree_results.json')}
def main():
    allids=set(); checks={}
    r7=ROOT.parents[1]/'graph_memory_round7'/'localization'/'scores_per_issue.json'
    earlier={r['id'] for r in json.loads(r7.read_text(encoding='utf8'))} if r7.exists() else None
    for panel,(seal,folder,result) in panels.items():
        hashes=load(seal)
        assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in hashes.items())
        data=load(result)
        records=[load(p.relative_to(ROOT)) for p in (ROOT/folder).glob('*.json')]
        tasks={r['task'] for r in records}
        assert not allids.intersection(tasks) and len(tasks)==len(records)
        allids.update(tasks)
        for r in records:
            if 'candidates' in r:
                candidates=r['candidates']
                methods=candidates[0]['ranks']
                assert len({c['id'] for c in candidates})==len(candidates)
                for m in methods:
                    assert sorted(c['ranks'][m] for c in candidates)==list(range(1,len(candidates)+1))
                    expected=sorted(candidates,key=lambda c:(-c['scores'][m],c['id']))
                    assert [c['ranks'][m] for c in expected]==list(range(1,len(candidates)+1))
                denom=r['n_corpus'] if panel=='loc_full' else 40
                assert len(candidates)==denom
            else:
                for order in r['top40'].values():
                    assert len(order)==len({o['id'] for o in order})==40
                    assert order==sorted(order,key=lambda c:(-c['score'],c['id']))
        for m,ms in data['means'].items():
            assert all(0<=v<=1 for v in ms.values())
            for me,val in ms.items():
                nums=[d['methods'][m][me] for d in data['details'].values()]
                assert abs(sum(nums)/len(nums)-val)<1e-10
        checks[panel]={'n_sample':len(tasks),'n_judged':len(data['details']),'n_corpus_instances':sum(r['n_corpus'] for r in records),'n_sealed_files':len(hashes),'overlap_prior_R7_localization':sorted(tasks & earlier) if earlier is not None else None}
    (ROOT/'verification.json').write_text(json.dumps(checks,indent=2))
    print(json.dumps(checks,indent=2))
if __name__=='__main__':main()
