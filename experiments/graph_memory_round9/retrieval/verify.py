"""Independent checks on artifact integrity, official membership, exposure and prefixes."""
from collections import Counter
from pathlib import Path
import json
from source import ROOT,R8,h,load_json,write_json,official_ids,member,base
def main():
    seal=load_json(ROOT/'blind_seal.json');stopseal=load_json(ROOT/'stop_seal.json')
    assert all(h((ROOT/f).read_bytes())==s for f,s in seal['local'].items())
    assert all(h((R8/f).read_bytes())==s for f,s in seal['r8'].items())
    assert all(h((ROOT/f).read_bytes())==s for f,s in stopseal.items())
    sample=load_json(ROOT/'sample.json')
    ids,sha=official_ids();selected=sample['selected'];tids={r['issue'] for r in selected}
    assert len(tids)==len(selected)==len({r['repo'] for r in selected})
    assert tids<=ids and not tids&{f.stem for f in (R8/'loc_predictions').glob('*.json')}
    assert sha==sample['official_split_sha256']
    res=load_json(ROOT/'results.json');sr=load_json(ROOT/'stop_results.json')
    n=0;sources=0;decoded=0;decisions=0;triples=0;null=0
    for r in selected:
        t=r['issue'];rec=load_json(ROOT/'predictions'/(t+'.json'))
        body=load_json(ROOT/'dense'/(t+'.json'));universe={x['id'] for x in body['candidates']}
        dense=sorted(universe,key={s:i for i,s in enumerate(rec['ranks']['dense'])}.__getitem__)
        dense_again=[x['id'] for x in sorted(body['candidates'],key=lambda c:(-c['dot'],c['id']))]
        assert dense==dense_again and len(universe)==r['functions']
        assert rec['seed']==dense[:6] and len(rec['seed'])==6
        by_target={}
        for source,leaf,target in rec['stored_edges']:
            assert source in rec['seed'] and source!=target and target.endswith('/'+leaf)
            by_target.setdefault(target,set()).add(source)
        for m,ranking in rec['ranks'].items():
            assert set(ranking)==universe and len(ranking)==len(universe)
            if m in ('bm25','dense'):continue
            assert ranking[:8]==dense[:8]
            chosen=rec['suggestions'][m]
            assert set(chosen)==set(ranking[:10])-set(dense[:10])
            if m=='corroborated':
                assert all(len(by_target[c])+int(c.rsplit('/',1)[-1] in rec['query_identifiers'])>=2 for c in chosen)
        short=load_json(ROOT/'stop_predictions'/(t+'.json'))['policies']
        for m,row in short.items():
            assert [s['source'] for s in row['trace']]==dense[:row['reads']]
            assert 1<=row['reads']<=6 and set(row['rank'])==universe and len(row['rank'])==len(universe)
        assert short['early3']['reads']<=short['early']['reads']<=short['fixed6']['reads']==6
        n+=len(universe);sources+=len(rec['seed']);decoded+=len(rec['seed'])-len(rec['failed_seed_ast'])
        triples+=len(rec['stored_edges']);decisions+=len(rec['suggestions']['corroborated']);null+=len(rec['suggestions']['matched'])
    assert n==sum(r['functions'] for r in selected)
    assert len(res['details'])==len(sr['details'])
    assert res['diagnostics']['maximum_absolute_acc10_rounding_difference']<=.000051
    facts=dict(official_split_sha256=sha,original_test_size=len(ids),study_n=len(tids),independent_repositories=len(tids),full_candidate_count=n,primary_predictions_sealed=len(seal['local']),companion_files_sealed=len(stopseal),six_seed_reads=sources,decoded_seed_functions=decoded,stored_provenance_triples=triples,corroborated_suggestions=decisions,matched_null_suggestions=null,official_acc10_check=res['diagnostics']['maximum_absolute_acc10_rounding_difference'])
    write_json(ROOT/'verification.json',facts);print(facts)
if __name__=='__main__':main()
