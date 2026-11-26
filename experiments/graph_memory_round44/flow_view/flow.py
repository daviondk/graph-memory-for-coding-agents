"""Materialize query-independent two-bit value-flow features over each committed tool group."""
from collections import Counter,defaultdict
import gzip,hashlib,json,os,sys
from pathlib import Path
from time import perf_counter_ns
for k in ('OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','OMP_NUM_THREADS'):os.environ[k]='1'
D=Path(__file__).resolve().parent;W=D.parents[1]
R42=W/'graph_memory_round42/causal_ablation';R21=W/'graph_memory_round21/incremental_binding'
sys.path.insert(0,str(R42))
from core42 import read,save,sha
sys.path.insert(0,str(W/'graph_memory_round41/prefix_native'))
import native
sys.path.insert(0,str(R21))
from stream import FeedIndex
from graph_memory.graphs.provenance.builder import _argument_contains,_typed_tokens
import numpy as np

class EndpointSums:
    def __init__(self):
        self.sums={}
    def apply(self,delta):
        for a,b,sign in delta:
            for key,slot in ((a,0),(b,1)):
                if key not in self.sums:self.sums[key]=[0,0]
                c=self.sums[key];c[slot]+=sign
                assert c[slot]>=0
                if not any(c):del self.sums[key]
    def flags(self):
        return {key:(int(x>0)+2*int(y>0)) for key,(x,y) in self.sums.items()}

class PairTable:
    def __init__(self):
        self.table={}
    def apply(self,delta):
        for a,b,sign in delta:
            old=self.table.get((a,b),0)+sign
            assert old>=0
            if old:self.table[a,b]=old
            else:del self.table[a,b]
    def flags(self):
        flags={}
        for a,b in self.table:
            flags[a]=flags.get(a,0)|1
            flags[b]=flags.get(b,0)|2
        return flags

def bytecount(x):
    return max(1,(int(x).bit_length()+6)//7)

def extract(events,has_content):
    # Independent writer. Shared deltas are released only at the end of a group.
    active={};unusable=set();seen={};names={};has=set()
    batch=[];boundaries=[];references=[];pending=0;total=Counter();raw_reference=FeedIndex()
    for e in events:
        raw_reference.consume(e)
        if e.event_type not in ('tool_call','tool_output'):continue
        name=e.call_id
        if e.event_type=='tool_call':
            assert name not in names
            names[name]=len(names);pending+=1
            for value,(owner,subs) in active.items():
                if _argument_contains(e,value):
                    subs.append(names[name]);batch.append((owner,names[name],1))
        else:
            cid=names[name]
            pending-=1;assert pending>=0
            if has_content(e.content):has.add(cid)
            for value in {v for _,v in _typed_tokens(e.content)}:
                if value in unusable:continue
                if value not in active:
                    active[value]=(cid,[])
                elif active[value][0]!=cid:
                    owner,subs=active.pop(value);unusable.add(value)
                    batch.extend((owner,sub,-1) for sub in subs)
            if not pending:
                edits=[(a,b,c) for a,b,c in batch if a in has and b in has]
                total['unavailable_witness_ops']+=len(batch)-len(edits);batch=[]
                total['adds']+=sum(c>0 for _,_,c in edits);total['retracts']+=sum(c<0 for _,_,c in edits)
                boundaries.append(edits)
                references.append({(names[a],names[b]):v for (a,b),v in raw_reference.support.items() if names[a] in has and names[b] in has})
    assert not batch and not pending and boundaries
    return boundaries,references,names,total

def check(t,steps,orig,stats):
    pair=PairTable();ends=EndpointSums();ever={};middle={};result=Counter(stats)
    peak=[0,0];mid=(len(steps)-1)//2
    for j,delta in enumerate(steps):
        pair.apply(delta);ends.apply(delta)
        fp=pair.flags();f=ends.flags()
        assert pair.table==orig[j] and fp==f
        ever={k:v|ever.get(k,0) for k,v in (ever|f).items()}
        extra=sum((v&~f.get(k,0)).bit_count() for k,v in ever.items())
        result['boundaries']+=1;result['live_flags']+=sum(v.bit_count() for v in f.values())
        result['stale_flags_monotone']+=extra;result['states_with_false_flags']+=bool(extra)
        result['pair_rows_across_states']+=len(pair.table);result['counter_rows_across_states']+=len(ends.sums)
        size_pair=sum(bytecount(a)+bytecount(b)+bytecount(v) for (a,b),v in pair.table.items())
        size_end=sum(bytecount(a)+bytecount(x)+bytecount(y) for a,(x,y) in ends.sums.items())
        result['pair_bytes_across_states']+=size_pair;result['counter_bytes_across_states']+=size_end
        peak=[max(peak[0],size_pair),max(peak[1],size_end)]
        if j==mid:middle=dict(f)
    result.update(dict(peak_pair_bytes=peak[0],peak_counter_bytes=peak[1],final_pair_bytes=size_pair,final_counter_bytes=size_end))
    return middle,result

def timed(steps,cls):
    v=cls();read_ns=write_ns=0;checksum=0
    for batch in steps:
        a=perf_counter_ns();v.apply(batch);b=perf_counter_ns();f=v.flags();end=perf_counter_ns()
        checksum+=sum(f.values())
        write_ns+=b-a;read_ns+=end-b
    return write_ns,read_ns,checksum

def experiment():
    assert sha(D/'PROTOCOL_RU.md')=='af463d1fdbf9a0dde327d0cbe2d9eff4c6a6730bc2c1ed067190c3a008205ee2'
    pilot=native.api.pilot
    tok=pilot.offsets(pilot.Tokenizer.from_file(str(pilot.CACHE/'tokenizer.json')))
    def has_content(text):
        return bool(pilot.token_chunks(text,tokenizer=tok,max_tokens=504,overlap_tokens=64))
    base_hash=read(R42/'manifest.json')['files']
    for sh in range(8):
        fn=D/f'trace-{sh}.json.gz';seal=D/f'shard-{sh}.json'
        if seal.exists():assert read(seal)['sha']==sha(fn);continue
        tab=R42/f'test-{sh}.npz';idx=R42/f'test-{sh}.json.gz'
        assert sha(tab)==base_hash[tab.name] and sha(idx)==base_hash[idx.name]
        items={r['q']:[c['node_id'] for c in r['rr']] for r in read(native.api.TR/f'forecasts-main-{sh}.json.gz')}
        expected=defaultdict(list)
        with np.load(tab) as z:
            edge=z['edge'];at=0
            for q,t,n,orig in read(idx):
                seq=[items[q][i] for i in orig];bits=(edge[at:at+n,4]>0).astype(int)+2*(edge[at:at+n,5]>0);at+=n
                expected[t].append((q,seq,bits))
            assert at==len(edge)
        out={}
        path=native.api.RAW/f'trajectories-{sh:05d}.jsonl'
        assert sha(path)==read(W/f'graph_memory_round41/prefix_native/forecast-{sh}-seal.json')['source']
        for _,row in pilot.stream(path):
            t=row['session_id']
            if t not in expected:continue
            tr=native.adapt_isetrace_record(native.parse_isetrace_record(row),source_revision=pilot.RAW[1])
            steps,ref,names,total=extract(tr.events,has_content)
            mid,counts=check(t,steps,ref,total)
            for q,seq,bits in expected[t]:
                got=[mid.get(names[k[len('output-content:'):].rsplit(':chunk:',1)[0]],0) if k.startswith('output-content:') else 0 for k in seq]
                assert np.array_equal(got,bits),(t,q)
                counts['official_candidate_rows']+=len(seq);counts['official_questions']+=1
            turns=[];direction=int(hashlib.sha256(t.encode()).hexdigest(),16)%2
            for rep in range(3):
                order=[PairTable,EndpointSums]
                if (rep+direction)%2:order.reverse()
                clocks={c.__name__:timed(steps,c) for c in order}
                assert clocks['PairTable'][2]==clocks['EndpointSums'][2]
                turns.append(clocks)
            out[t]=dict(counts=counts,timing=turns)
        assert set(out)==set(expected)
        save(fn,out);save(seal,dict(sha=sha(fn),code=sha(Path(__file__)),protocol=sha(D/'PROTOCOL_RU.md'),native=sha(tab),source=sha(path)))
        print('verified shard',sh,len(out),flush=True)

if __name__=='__main__':experiment()
