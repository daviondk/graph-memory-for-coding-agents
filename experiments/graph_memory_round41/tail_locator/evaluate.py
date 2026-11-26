"""Open the later receipt as a backing file; count actual process-level reads per policy."""
from collections import Counter,defaultdict
from hashlib import sha256
from pathlib import Path
import json
from tempfile import TemporaryFile
import pyarrow.parquet as pq
from source import D,RAW,h,digest,read,save
from locator import Access,probe,full_scan,selftest

def main():
    seal=read(D/'panel-seal.json');assert digest(D/'panel.json.gz')==seal['files']['panel'] and digest(D/'tails.json.gz')==seal['files']['tails']
    suite=selftest();protocol=read(D/'method-seal.json')
    assert protocol['locator']==digest(D/'locator.py') and protocol['evaluator']==digest(D/'evaluate.py')
    panel=read(D/'panel.json.gz');tails=read(D/'tails.json.gz');wanted=defaultdict(lambda:defaultdict(list))
    for i,row in enumerate(panel):
        if row[2] is not None:wanted[row[0]][row[2]].append(i)
    outcomes={};availability=Counter();lookup={}
    for ref in read(RAW/'files.json')['events']:
        path=RAW/ref['file'];assert digest(path)==ref['sha']
        pf=pq.ParquetFile(path)
        for batch in pf.iter_batches(columns=['run_id','event_index','event_json'],batch_size=256):
            ridc,evc,rawc=batch.columns
            for j,(r,at) in enumerate(zip(ridc.to_pylist(),evc.to_pylist())):
                if r not in lookup:lookup[r]=h(r)
                rid=lookup[r]
                if at not in wanted.get(rid,{}):continue
                indices=wanted[rid].pop(at);ob=json.loads(rawc[j].as_py())['raw']['observation']
                assert ob['command']=='str_replace' and not ob['is_error'] and all(h(ob['path'])==panel[i][5] for i in indices)
                text=ob.get('old_content')
                availability['matched_view_receipt_pairs']+=len(indices);availability['distinct_receipts']+=1
                if isinstance(text,str):availability['with_before_pairs']+=len(indices)
                relevant=[i for i in indices if panel[i][8]=='tail']
                if not relevant:continue
                if not isinstance(text,str):
                    for i in relevant:outcomes[i]={'status':'missing_snapshot'}
                    continue
                data=text.encode('utf8');version=sha256(data).hexdigest()
                with TemporaryFile(dir=D) as file:
                    file.write(data);file.flush()
                    for i in relevant:
                        row=panel[i];token=[tuple(t) for t in tails[row[9]]];local=Access(file);global_store=Access(file)
                        bound,status=probe(local,token,row[6])
                        allspans,nrows,terminal=full_scan(global_store,token)
                        assert global_store.byte_count==len(data) and local.byte_count<=min(len(data),sum(v[0] for v in token)+2*len(token)+4)
                        if bound is not None:assert bound in [x[:3] for x in allspans]
                        if row[6]=='finite':goals={min(row[7],nrows)}|({min(row[7],nrows-1)} if terminal else set())
                        elif row[6]=='eof':goals={nrows}|({nrows-1} if terminal else set())
                        else:goals=set()
                        endpoint_matches=[s for s in allspans if s[4] in goals]
                        outcomes[i]=dict(status=status,span=bound,placements=len(allspans),unique_placement=allspans[0] if len(allspans)==1 else None,
                            valid_end_matches=len(endpoint_matches),tail_lines=len(token),bytes_read=local.byte_count,read_calls=local.calls,full_read=global_store.byte_count,full_calls=global_store.calls,
                            revision=version,terminal_lf=terminal,crlf=b'\r\n' in data)
    assert not any(wanted.values())
    assert len(outcomes)==sum(r[8]=='tail' and r[2] is not None for r in panel)
    sealed=save('outcomes.json.gz',outcomes)
    save('score-seal.json',dict(method=digest(D/'method-seal.json'),outcomes=sealed,availability=availability,fixtures=suite))
    print(dict(availability),len(outcomes),Counter(x['status'] for x in outcomes.values()))
if __name__=='__main__':main()
