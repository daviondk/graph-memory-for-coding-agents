"""Project official graphs to disk, with source attestations and without loading test labels."""
from pathlib import Path
from collections import defaultdict
import hashlib,sys,sqlite3
ROOT=Path(__file__).resolve().parent
TR=ROOT.parents[1]/'graph_memory_round19/trained_rank'
sys.path.insert(0,str(TR))
from prepare import pilot,load,put,RAW,RUN as TRAINED,R18
from project import CACHE
RUN=Path('D:/CodexResearch/x20-isetrace-residual')
def h(s):return hashlib.sha256(s.encode('utf8')).digest()
def inventory(i):
    splits=load(TR/'split.json.gz');by={r['t']:s for s,rs in splits.items() for r in rs}
    wanted={r['q']:r['t'] for rs in splits.values() for r in rs}
    qs=defaultdict(list)
    for _,r in pilot.stream(pilot.Q):
        if r['id'] in wanted:qs[wanted[r['id']]].append((r['id'],r['query']))
    from graph_memory.datasets.isetrace.adapter import parse_isetrace_record,adapt_isetrace_record
    source=RAW/f'trajectories-{i:05d}.jsonl'
    assert pilot.sha(source)==next(x['sha256'] for x in load(R18/'isetrace_official/source-lock.json') if x['path']=='trajectories/'+source.name)
    tok=pilot.offsets(pilot.Tokenizer.from_file(str(pilot.CACHE/'tokenizer.json')))
    db=sqlite3.connect(RUN/f'strings{i}.sqlite');db.execute('create table if not exists x(k blob primary key,txt text,n int,base int) without rowid')
    graphs={}
    for raw,obj in pilot.stream(source):
        t=obj['session_id']
        if t not in by:continue
        tr=adapt_isetrace_record(parse_isetrace_record(obj),source_revision=pilot.RAW[1])
        g=pilot.native.build_provenance_graph(tr,content_chunker=lambda s:pilot.token_chunks(s,tokenizer=tok,max_tokens=504,overlap_tokens=64))
        pool=pilot.native.provenance_unit_candidates(g);ids={c.item_id for c in pool}
        pp=(TRAINED/'projection'/by[t]/f'{t}.json.gz') if by[t]!='test' else CACHE/'projection'/f'{i}-{t}.json.gz'
        old=load(pp);assert [c.item_id for c in pool]==[v['item_id'] for v in old['pool']]
        assert all(c.text==v['text'] for c,v in zip(pool,old['pool'],strict=True))
        rows=[('passage: '+n.text,by[t]=='train' and n.node_id in ids) for n in g.nodes]
        rows+=[('query: '+text,by[t]=='train') for _,text in qs[t]]
        db.executemany('insert into x values(?,?,?,?) on conflict(k) do update set base=max(base,excluded.base)',[(h(s),s,len(s),int(b)) for s,b in rows])
        p=RUN/'graphs'/f'{i}-{t}.json.gz';put(p,dict(t=t,split=by[t],q=qs[t],g=g.model_dump(),raw_source=hashlib.sha256(raw).hexdigest()))
        graphs[t]=pilot.sha(p)
    db.commit();db.close();put(RUN/f'graphs-{i}.json',graphs);print(i,len(graphs),flush=True)
def protocol():
    names=['PROTOCOL_RU.md','setup_graph.py']
    put(ROOT/'protocol-lock.json',dict(files={n:pilot.sha(ROOT/n) for n in names},split=pilot.sha(TR/'split.json.gz'),checkpoint=pilot.sha(TR/'trained-checkpoint.json'),r19_trained=pilot.sha(TR/'MANIFEST_SHA256.json')))
if __name__=='__main__':
    if sys.argv[1]=='lock':protocol()
    else:
        for n in sys.argv[1:]:inventory(int(n))

