"""Reconstruct native source-only retrieval requests, independent of any scoring file."""
from collections import defaultdict
import gzip, hashlib, json, os, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
OFF=ROOT.parent/'isetrace_official'
sys.path.insert(0,str(OFF))
import rank
from discover import pilot, RAW
from graph_memory.datasets.isetrace.adapter import parse_isetrace_record,adapt_isetrace_record
from graph_memory.retrieval.requests.text import TextCandidate
from graph_memory.embeddings.dense import format_dense_query,format_dense_passage
CACHE=Path(os.environ.get('ISE_E5_CACHE','D:/CodexResearch/x20-isetrace-e5-gpu/cache'))
W=pilot.CACHE.parent/'e5-base-v2'
def load(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix=='.gz' else b)
def put(p,obj,compress=4):
    b=(json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
    if p.suffix=='.gz':b=gzip.compress(b,compresslevel=compress,mtime=0)
    p.parent.mkdir(exist_ok=True,parents=True)
    tmp=p.with_name(p.name+'.tmp');tmp.write_bytes(b);tmp.replace(p)
def split():
    return {r['query_id']:r['trajectory_id'] for r in load(OFF/'cohort.json')}
def audit_ids():
    return set(sorted(set(split().values()),key=lambda t:hashlib.sha256(('r18-e5-fp32/'+t).encode()).digest())[:32])
def reqs(row):
    pool=tuple(TextCandidate.model_validate(x) for x in row['pool'])
    return [pilot.TextRankingRequest(task_id=q,query_text=s,candidates=pool) for q,s in row['q']]
def strings(row):
    return [format_dense_query(r,query_prefix='query: ') for r in reqs(row)]+[format_dense_passage(c,passage_prefix='passage: ') for c in reqs(row)[0].candidates]
def shard(i):
    ids=split();by=defaultdict(list)
    for _,q in pilot.stream(pilot.Q):
        if q['id'] in ids:by[ids[q['id']]].append((q['id'],q['query']))
    source=RAW/f'trajectories-{i:05d}.jsonl'
    locks={r['path']:r['sha256'] for r in load(OFF/'source-lock.json')}
    assert pilot.sha(source)==locks['trajectories/'+source.name]
    tok=pilot.offsets(pilot.Tokenizer.from_file(str(pilot.CACHE/'tokenizer.json')))
    count=0
    for raw,obj in pilot.stream(source):
        t=obj['session_id']
        if t not in by:continue
        dest=CACHE/'projection'/f'{i}-{t}.json.gz'
        if not dest.exists():
            tr=adapt_isetrace_record(parse_isetrace_record(obj),source_revision=pilot.RAW[1])
            graph=pilot.native.build_provenance_graph(tr,content_chunker=lambda s:pilot.token_chunks(s,tokenizer=tok,max_tokens=504,overlap_tokens=64))
            pool=pilot.native.provenance_unit_candidates(graph)
            fields={**{a.event_id:a.raw_arguments for a in tr.tool_calls},**{a.event_id:a.content for a in tr.tool_outputs}}
            put(dest,dict(t=t,i=i,q=by[t],pool=[c.model_dump() for c in pool],fields=fields,source_sha256=hashlib.sha256(raw).hexdigest()))
        count+=1
    print(i,count,flush=True)
if __name__=='__main__':
    shard(int(sys.argv[1]))
