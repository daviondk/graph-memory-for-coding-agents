"""Measure complete native provenance graph feature sizes directly, without embeddings or labels."""
from collections import defaultdict
import gzip,hashlib,itertools,os,sqlite3,sys,time
import numpy as np
from prepare import ROOT,RUN,RAW,pilot,load,put
from project import CACHE
def keys(s):return hashlib.sha256(s.encode()).digest()
def shard(i):
    splits=load(ROOT/'split.json.gz');by=defaultdict(list)
    for s,records in splits.items():
        for r in records:by[r['t']].append((s,r['q']))
    qs={}
    wanted={q for lst in by.values() for _,q in lst}
    for _,q in pilot.stream(pilot.Q):
        if q['id'] in wanted:qs[q['id']]=q['query']
    from graph_memory.datasets.isetrace.adapter import parse_isetrace_record,adapt_isetrace_record
    tok=pilot.offsets(pilot.Tokenizer.from_file(str(pilot.CACHE/'tokenizer.json')))
    dest=RUN/'shape';dest.mkdir(exist_ok=True);records=[];uk=defaultdict(set)
    for blob,obj in pilot.stream(RAW/f'trajectories-{i:05d}.jsonl'):
        t=obj['session_id']
        if t not in by:continue
        tr=adapt_isetrace_record(parse_isetrace_record(obj),source_revision=pilot.RAW[1])
        g=pilot.native.build_provenance_graph(tr,content_chunker=lambda s:pilot.token_chunks(s,tokenizer=tok,max_tokens=504,overlap_tokens=64))
        s=by[t][0][0];ss=['passage: '+v.text for v in g.nodes];qtxt=['query: '+qs[q] for _,q in by[t]];uk[s].update(keys(x) for x in itertools.chain(ss,qtxt))
        graph_bytes=len(g.model_dump_json().encode());wire=sum(len(x.encode()) for x in ss);pu=pilot.native.provenance_unit_candidates(g)
        records.append(dict(t=t,split=s,qs=len(qtxt),nodes=len(g.nodes),edges=len(g.edges),graph_json_bytes=graph_bytes,passage_text_bytes=wire,pu=len(pu)))
    for s,hashes in uk.items():(dest/f'{i}-{s}.sha.gz').write_bytes(gzip.compress(b''.join(sorted(hashes)),compresslevel=1,mtime=0))
    put(dest/f'{i}.json.gz',records)
    print(i,len(records),flush=True)
def summarize():
    src=RUN/'shape';rows=[r for i in range(8) for r in load(src/f'{i}.json.gz')];splits=load(ROOT/'split.json.gz')
    inst={k:[] for k in splits};unique={};by={r['t']:r for r in rows}
    testkeys={k for (k,) in sqlite3.connect((CACHE/'vectors.sqlite3').resolve().as_uri()+'?mode=ro',uri=True).execute('select k from corpus')}
    result={}
    for s,rr in splits.items():
        keys_set=set()
        for i in range(8):
            raw=gzip.decompress((src/f'{i}-{s}.sha.gz').read_bytes());assert len(raw)%32==0;keys_set.update(raw[j:j+32] for j in range(0,len(raw),32))
        unique[s]=keys_set; per=[by[r['t']] for r in rr]; ts={r['t'] for r in rr}
        emb_rows=sum(1+r['nodes'] for r in per); edges=sum(r['edges'] for r in per)
        # Per-task tensorization uses forward and reversed native edges; query node is present once per request.
        result[s]=dict(queries=len(rr),trajectories=len(ts),graph_nodes_per_unique_trajectory=sum(by[t]['nodes'] for t in ts),edges_per_unique_trajectory=sum(by[t]['edges'] for t in ts),
            encoder_rows_by_query=emb_rows,persisted_fp32_feature_gib=emb_rows*768*4/2**30,raw_forward_edges_by_query=edges,unique_strings=len(keys_set),cached_strings_available=len(testkeys&keys_set),
            graph_serialized_gib=sum(by[t]['graph_json_bytes'] for t in ts)/2**30,all_candidate_text_gib_by_query=sum(r['passage_text_bytes'] for r in per)/2**30,
            max_nodes=max(r['nodes']+1 for r in per),max_forward_edges=max(r['edges'] for r in per),mean_nodes=emb_rows/len(rr),mean_forward_edges=edges/len(rr))
        sizes=[r['nodes']+1 for r in per];es=[2*r['edges'] for r in per]
        rng=np.random.default_rng(13);batch_nodes=[];batch_edges=[]
        for rep in range(15):
            perm=rng.permutation(len(rr))
            for ix in range(0,len(rr)-127,128):
                jj=perm[ix:ix+128];batch_nodes.append(sum(sizes[j] for j in jj));batch_edges.append(sum(es[j] for j in jj))
        result[s]['128_batch']={k:[float(v) for v in np.quantile(arr,[.5,.95,1])] for k,arr in [('nodes',batch_nodes),('bidirectional_edges',batch_edges)]}
    total=set.union(*unique.values());td=unique['train']|unique['dev']
    put(ROOT/'rgcn-shapes.json.gz',rows);put(ROOT/'rgcn-feasibility.json',dict(splits=result,
        train_dev_unique=len(td),all_splits_unique=len(total),all_missing_independent_of_test=len(total-testkeys),train_dev_missing_from_test=len(td-testkeys),all_supplied_test_keys_present=len(testkeys&total),
        train_dev_mmap_gib=sum(result[s]['persisted_fp32_feature_gib'] for s in ['train','dev'])))
if __name__=='__main__':
    if sys.argv[1]=='summary':summarize()
    else:
        for a in sys.argv[1:]:shard(int(a))
