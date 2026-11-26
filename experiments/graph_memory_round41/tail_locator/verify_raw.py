"""Independent byte-for-byte comparison on archived views and before-snapshots; no code execution."""
from collections import defaultdict
from hashlib import sha256
from io import BytesIO
import json
import pyarrow.parquet as pq
from source import D,RAW,read,digest,h,save
from detector import gate
from examine import display

def collect(wanted,callback):
    runs={}
    for entry in read(RAW/'files.json')['events']:
        p=RAW/entry['file'];assert digest(p)==entry['sha']
        file=pq.ParquetFile(p)
        for g in range(file.num_row_groups):
            keys=file.read_row_group(g,columns=['run_id','event_index'])
            hits=[]
            for i,(r,at) in enumerate(zip(keys.column(0).to_pylist(),keys.column(1).to_pylist())):
                if r not in runs:runs[r]=h(r)
                if (runs[r],at) in wanted:hits.append((i,(runs[r],at)))
            if not hits:continue
            event=file.read_row_group(g,columns=['event_json']).column(0)
            for i,key in hits:callback(key,json.loads(event[i].as_py())['raw']['observation'])
def parse_lines(data):
    out=[];source=BytesIO(data)
    while True:
        pos=source.tell();line=source.readline()
        if not line:break
        content=line.removesuffix(b'\n')
        if line.endswith(b'\r\n'):content=content[:-1]
        out.append((content,pos,pos+len(content)))
    if not data or data.endswith(b'\n'):out.append((b'',len(data),len(data)))
    return out

def main():
    panel=read(D/'panel.json.gz');tails=read(D/'tails.json.gz')
    scores={int(i):r for i,r in read(D/'outcomes.json.gz').items()};viewmap={};source=defaultdict(list);case_lines={}
    for i in scores:
        r=panel[i];viewmap[r[0],r[1]]=r[9];source[r[0],r[2]].append(i)
    def display_original(key,ob):
        seen,_,_=display(ob);_,boundary=gate(ob);tail=[seen[n].encode() for n in sorted(seen) if n>=boundary['cut']]
        signature=viewmap[key]
        assert [[len(v),sha256(v).hexdigest()] for v in tail]==tails[signature]
        case_lines[key]=tail
    collect(viewmap,display_original);assert set(case_lines)==set(viewmap)
    checked=set();totals=defaultdict(int)
    def validate(key,ob):
        data=ob['old_content'].encode();lines=parse_lines(data);index=defaultdict(list)
        for j,(s,_,_) in enumerate(lines):index[s].append(j)
        for i in source[key]:
            r=panel[i];out=scores[i];tail=case_lines[r[0],r[1]];n=len(tail);allmatches=[]
            for start in index[tail[0]]:
                segment=lines[start:start+n]
                if [v[0] for v in segment]!=tail:continue
                a=segment[0][1];b=segment[-1][2]
                allmatches.append([a,b,sha256(data[a:b]).hexdigest(),start+1,start+n])
            assert sha256(data).hexdigest()==out['revision'] and len(data)==out['full_read']
            assert len(allmatches)==out['placements']
            if len(allmatches)==1:assert allmatches[0]==out['unique_placement']
            if out['span'] is not None:
                assert tuple(out['span']) in [tuple(t[:3]) for t in allmatches];totals['accepted_byte_ranges']+=1;totals['accepted_rendered_lines']+=n
            checked.add(i);totals['literal_scans']+=1;totals['rendered_lines']+=n
    collect(source,validate);assert checked==set(scores)
    save('literal-audit.json',dict(counts=totals,distinct_views=len(viewmap),distinct_snapshots=len(source),native=digest(D/'outcomes.json.gz'),raw=digest(RAW/'files.json')))
    print(dict(totals),len(viewmap),len(source))
if __name__=='__main__':main()
