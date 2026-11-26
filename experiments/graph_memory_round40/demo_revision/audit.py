"""Rebuild the primary numeric claims from the sibling sealed experiment results."""
import hashlib,json
from pathlib import Path
D=Path(__file__).resolve().parent
R39=D.parents[1]/'graph_memory_round39'
R40=D.parent

def get(path):return json.loads((R39/path).read_bytes())

def evidence():
    source_names=['global_packet/results.json','budget_curve/results.json','packet_invalidation/results.json','exact_certificate/results.json','fixed_point/benchmark.json','fixed_point/withdrawals.json','fixed_point/seal.json','provenance_packet_demo/results.json']
    g,curve,inv,exact,fixed,withdraw,seal,panel=map(get,source_names)
    source={p:hashlib.sha256((R39/p).read_bytes()).hexdigest() for p in source_names}
    assert (curve['n'],curve['trajectories'],len(curve['seeds']))==(2000,1207,5)
    assert abs(g['means']['graph-dp'][0]-.826)<1e-12 and abs(g['means']['R35-firstfit'][0]-.8219)<1e-12
    assert round(g['means']['graph-dp'][2],2)==2039.12 and round(g['means']['R35-firstfit'][2],2)==2039.30
    metrics=curve['metrics']; ix=metrics.index('FullSupport@2048');native={k:curve['means'][k][ix] for k in curve['arms']}
    assert abs(native['wo_chunk_adjacency/graph_dp']-.8307)<1e-12
    assert inv['exact_cached']==2041 and inv['sources']==2528 and round(inv['full_vs_cert_ratio'],2)==5.16
    totals={k:sum(r[k] for r in exact['counts'].values()) for k in ('treatments','unchanged','false_negative','false_positive','avoidable_barrier_recompute')}
    assert totals==dict(treatments=108204,unchanged=73261,false_negative=0,false_positive=0,avoidable_barrier_recompute=264)
    assert fixed['rows']==10000 and all(s['32']['changed']==0 for s in fixed['seeds'].values()) and withdraw['float_same']==108204
    contrasts={k:dict(delta_pp=round(a['delta'][0]*100,5),crossed_ci_pp=[round(x[0]*100,4) for x in a['ci95_crossed']]) for k,a in g['contrasts'].items() if k.endswith(('R35-firstfit','rgcn/strict','adjacency/strict','rgcn/firstfit','adjacency/firstfit'))}
    auc=curve['contrasts']['R35/firstfit']
    return dict(source_hashes=source,questions=curve['n'],trajectories=curve['trajectories'],seeds=curve['seeds'],budgets=curve['budgets'],native_fs=native,contrasts=contrasts,global_means={k:v for k,v in g['means'].items() if k in ('graph-dp','dense-dp','graph-rankdp','graph-greedy','R35-firstfit')},auc=dict(graph=curve['means']['R35/graph_dp'][0],firstfit=curve['means']['R35/firstfit'][0],delta=auc['delta'][0],crossed_ci=[v[0] for v in auc['crossed_ci']]),certificate={k:inv[k] for k in ('sources','exact_cached','changed','boundary_only','full_vs_cert_ratio','cluster_ratio_ci','macro_cache_rate','median_and_p95_us','mean_extra_build_us')},exact=exact['counts'],synthetic=exact['synthetic'],q32=dict(original=fixed['rows'],exclusions=withdraw['float_same'],seal=seal),panel=panel['arms'])
if __name__=='__main__':
    result=evidence()
    controls=R39/'hybrid_controls/results.json'
    paths=R40/'natural_invalidations/results.json'
    for source in (controls,paths):
        sha=hashlib.sha256(source.read_bytes()).hexdigest()
        assert sha==json.loads((source.parent/'manifest.json').read_bytes())['files'][source.name]
        result['source_hashes'][str(source.relative_to(D.parents[1])).replace('\\','/')]=sha
    h=json.loads(controls.read_bytes());n=json.loads(paths.read_bytes())['groups'];prefix='wo_chunk_adjacency/'
    within=h['contrasts'][prefix+'graph_dp minus '+prefix+'firstfit'];cheap=h['contrasts'][prefix+'graph_dp minus '+prefix+'graph_value']
    def points(v):return round(100*v,3)
    assert [points(h['means'][prefix+k][1]) for k in ('graph_dp','firstfit')]==[83.07,81.19]
    assert [points(within['delta'][1])]+[points(row[1]) for row in within['ci95_crossed']]==[1.88,.758,3.067]
    assert [points(h['means'][prefix+k][0]) for k in ('graph_dp','graph_value')]==[71.324,71.204]
    assert [points(cheap['delta'][0])]+[points(row[0]) for row in cheap['ci95_crossed']]==[.12,-.053,.298]
    result['offline_hybrid']={'fs2048':[.8307,.8119],'delta_pp':1.88,'ci_pp':[.758,3.067],'auc_pct':[71.324,71.204],'delta_auc_pp':.120,'ci_auc_pp':[-.053,.298]}
    present=n['pooled']['all_present'];total=n['pooled']['all']
    assert [present['n'],present['totals']['actual_safe'],total['n'],total['totals']['actual_safe'],total['issues'],total['repos']]==[2820,6,3525,711,37,5]
    result['coding_write_boundary']={'eligible':2820,'eligible_sufficient_reuse':6,'all':3525,'all_sufficient_reuse':711,'tasks':37,'repos':5}
    data=(json.dumps(result,sort_keys=True,indent=2)+'\n').encode();out=D/'evidence.json'
    if out.exists():assert out.read_bytes()==data
    else:out.write_bytes(data)
    print('All manuscript result sources checked.')
