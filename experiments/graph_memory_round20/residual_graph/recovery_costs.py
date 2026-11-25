"""Write per-model cost receipts as soon as every required database key is verified."""
from pathlib import Path
import hashlib
import json
import re
import sqlite3
import sys

HERE=Path(__file__).resolve().parent
RUN=Path('D:/CodexResearch/x20-isetrace-residual')
LOGS=RUN/'logs'

def read(p):
    return json.loads(p.read_bytes())

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def write(m):
    assert m in ('ft','base')
    plan=read(HERE/'vectors-plan.json')
    initial=read(HERE/'gpu-outage.json')
    dev=read(HERE/'cost-dev.json')
    resumed=read(HERE/f'gpu-resume-{m}.json') if (HERE/f'gpu-resume-{m}.json').exists() else {}
    full_log=LOGS/'full-cpu.progress.jsonl'
    full_rows=[r for line in full_log.read_text('utf8').splitlines() if (r:=json.loads(line))['mode']==m] if full_log.exists() else []
    cached=plan['copied']['r19ft']+plan['copied']['bounded_ft']+dev['encoded'] if m=='ft' else plan['copied']['r18_base']
    con=sqlite3.connect((RUN/'vectors.sqlite3').resolve().as_uri()+'?mode=ro',uri=True,timeout=120)
    constraint='1' if m=='ft' else 's.base=1'
    sql='select count(*) from corpus s where '+constraint+' and not exists(select 1 from vectors v where v.k=s.k and v.prec=?)'
    missing=con.execute(sql,[m]).fetchone()[0]
    actual=con.execute('select count(*) from vectors where prec=?',[m]).fetchone()[0]
    con.close()
    expect=plan['unique' if m=='ft' else 'base_required']
    assert missing==0 and actual==expect, (m,missing,actual,expect)
    prior=initial['committed'][m]-cached
    assert prior==(196608 if m=='ft' else 0)
    precpu=LOGS/'fallback.log'
    last={}
    for line in precpu.read_text('utf8').splitlines():
        fields=re.fullmatch(r'hash64 (ft|base) (\d+) (\d+) ([0-9.]+)',line)
        if fields:
            mode,idx,need,seconds=fields.groups()
            last[mode]=(int(idx),int(need),float(seconds))
    receipts=[]
    for tag in ('availability','hash64'):
        path=HERE/'cpu_fallback'/tag/'cpu-encoding.json'
        if path.exists():
            receipts.append({'tag':tag,**read(path)[m]})
    unique=actual-cached
    accounted_rows=prior+resumed.get('new',0)+sum(r['inserted'] for r in full_rows)+sum(r['new'] for r in receipts)
    prebooked=unique-accounted_rows
    assert prebooked>=0
    partial_seconds=last.get(m,(0,0,0.0))[-1] if prebooked else 0.0
    token_lower=(43641325 if m=='ft' else 0)+resumed.get('tokens',0)+sum(r['model_tokens'] for r in full_rows)+sum(r['tokens'] for r in receipts)
    time_lower=(890.3 if m=='ft' else 0.)+resumed.get('seconds',0.)+sum(r['seconds'] for r in full_rows)+sum(r['seconds'] for r in receipts)+partial_seconds
    out=dict(complete=actual,expected=expect,missing=missing,preexisting=cached,encoded=unique,tokens=token_lower,seconds=time_lower,
          token_measurement='Lower bound from finished stage meters and per-batch CPU ledger. Interrupted cohort tokens without a terminal receipt are excluded.',
          time_measurement='Sum across device streams, potentially overlapping in real time, lower bound. Includes the last printed time for the interrupted hash64 stage; no downtime.',
          partial_cpu_rows_without_terminal_cost=prebooked,partial_preboot_seconds_lower_bound=partial_seconds,
          original_gpu_committed=prior,resumed_gpu=resumed,cpu_full_committed=sum(r['inserted'] for r in full_rows),cohort_encodings=receipts,
          vector_plan_sha256=sha(HERE/'vectors-plan.json'),preboot_log_sha256=sha(precpu),gpu_outage_sha256=sha(HERE/'gpu-outage.json'))
    target=HERE/f'cost-{m}.json'
    if target.exists():
        assert read(target)==out, 'Existing receipt differs'
    else:
        temp=target.with_suffix('.staging')
        temp.write_text(json.dumps(out,sort_keys=True,separators=(',',':'))+'\n',encoding='utf8')
        temp.replace(target)
    print(m,'all keys verified',actual,'uncounted cost rows',prebooked,flush=True)

if __name__=='__main__':
    write(sys.argv[1])
