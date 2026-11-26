"""Verify the portable projections, address transitions, hashes, and independent exact DP."""
from hashlib import sha256
import json
from pathlib import Path
from app import CASES, D, audit, db, packet

def dense(blocks):
    used=0;head=[]
    for row in blocks:
        if used+row['cost']>1024:break
        head.append(row['unit']);used+=row['cost']
    cap=2048-used;best=[0]*(cap+1);decisions=[]
    for row in blocks[len(head):]:
        w=row['cost'];g=row['gain'];old=best;best=list(old);pick=bytearray(cap+1)
        for k in range(w,cap+1):
            if old[k-w]+g>old[k]:best[k]=old[k-w]+g;pick[k]=1
        decisions.append((row['unit'],w,pick))
    tail=[]
    for unit,w,pick in reversed(decisions):
        if pick[cap]:tail.append(unit);cap-=w
    return head+tail[::-1]

def check():
    if (D/'manifest.json').is_file():
        for name,h in json.loads((D/'manifest.json').read_bytes())['files'].items():assert sha256((D/name).read_bytes()).hexdigest()==h,name
    binding=json.loads((D/'source-bindings.json').read_bytes())['cases'];count=0
    for dataset,tables in [('reader.sqlite',{'receipt','block'}),('witness.sqlite',{'snapshot','address','witness'})]:
        c=db(dataset)
        try:
            assert {r[0] for r in c.execute("SELECT name FROM sqlite_schema WHERE type='table'") }==tables
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        finally:c.close()
    for case in CASES:
        s=packet(case);v=audit(case);expected=binding[case];interval=v['snapshot'];ev=s['receipt']
        blocks=s['blocks'];check_kept=[];audited=0;old_bad=new_bad=created=chosen_bad=0
        assert 'snapshot' not in s and not any('seen' in b or 'sha' in b for b in blocks)
        for b in blocks:
            i=b['unit'];c=v['blocks'][i];keep=c['old_end']<=interval['change_begin'] or c['old_start']>=interval['change_end']
            assert keep==b['kept'] and keep==(c['new_start'] is not None)
            if not keep:continue
            check_kept.append(b)
            move=ev['line_delta'] if b['low']>ev['high'] else 0
            assert (b['low']+move,b['high']+move)==(b['new_low'],b['new_high'])
            assert c['new_start']>=0 and c['new_end']<=interval['new_size']
            lines=c['lines'];assert [r['n'] for r in lines]==list(range(b['low'],b['high']+1))
            for row in lines:
                assert row['new_n']==row['n']+move
                for h in ('seen','before_sha','after_sha'):assert len(bytes.fromhex(row[h]))==32
                prior=row['seen']==row['before_sha'];post=row['seen']==row['after_sha']
                old_bad+=not prior;new_bad+=not post;created+=prior and not post
                chosen_bad+=(not post) and i in s['baseline']['ids'];audited+=1
        assert dense(blocks)==s['baseline']['ids']==expected['expected_old']
        assert dense(check_kept)==s['span']['ids']==expected['expected_new'] and dense([])==s['file']['ids']==[]
        assert [audited,old_bad,new_bad,created,chosen_bad]==[expected[k] for k in ('audited_lines','prior_mismatch','post_mismatch','new_mismatch','selected_post_mismatch')]
        assert [s['file_reuse'],s['range_reuse']]==[bool(expected['file_reuse']),bool(expected['range_reuse'])]
        assert v['verified_reuse']==(case=='relocated');count+=audited
    assert count==611
    print('Three cases verified: nine independently solved packets and 611 line-hash triples.')
if __name__=='__main__':check()
