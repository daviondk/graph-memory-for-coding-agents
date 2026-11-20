"""Validate native model request/response lineage, causal packet rendering and grader-side references."""
import collections,gzip,hashlib,json,statistics,sys
from common import ROOT,rows,pages
from policy import render
from pipeline import snapshots
from live_score import ast_id,sha
from verify import load,verify_filemap
L=ROOT/'live';P=L/'capsule_calls'
def stable(obj):return json.dumps(obj,sort_keys=True,ensure_ascii=True,separators=(',',':')).encode()
def main():
    from live_score import summary,grade
    verify_filemap(load(P/'prediction_lock.json'),P);verify_filemap(load(L/'grader_lock.json'));verify_filemap(load(L/'live_input_lock.json'))
    jobs={(r['id'],r['arm']):r for r in load(L/'reader_inputs.json')};cases={r['instance']:r for r in load(L/'cohort.json')};gold={r['id']:r for r in load(L/'outcomes.json')};scored={(r['id'],r['arm']):r for r in load(L/'actions_scored.json')}
    assert len(jobs)==64 and len(cases)==32 and cases.keys()==gold.keys()
    idx={(r['instance'],r['cut']):r for r in cases.values()};seen=set();native=collections.defaultdict(lambda:collections.defaultdict(list));spec=set()
    for k in range(8):
        sealed={(i,t):d for i,t,d in rows(ROOT/'sealed'/f'{k}.jsonl.gz') if (i,t) in idx}
        for it in rows(ROOT/'source/test'/f'{k}.jsonl.gz'):
            iid=it['instance']
            if iid not in cases:continue
            rec=cases[iid];g=gold[iid];t=rec['cut'];seen.add(iid)
            state=next(ss for step,ss,m in snapshots(it) if step==t);pg=pages(state['rebase']);assert it['instance']==g['id']
            for a in ('joint','rebased_tail'):
                ids,cost=sealed[iid,t]['512'][a];wire='\n'.join(render(pg[i]) for i in ids)
                assert jobs[iid,a]['packet_tokens']==cost and jobs[iid,a]['messages'][1]['content']=='Problem description:\n'+it['issue'][:3500]+'\n\nFile to edit: '+rec['path']+'\n\nArchived code observations:\n'+wire+'\n\nReturn exactly one JSON object.'
            snap=gzip.decompress((L/'snapshots'/g['snapshot']).read_bytes());assert sha(snap)+'.txt.gz'==g['snapshot'] and ast_id(snap.decode())==g['pre_ast_sha']
            rf=g['base_reference'];blob=gzip.decompress((L/'references'/(rf['blob_sha256']+'.gz')).read_bytes());assert sha(blob)==rf['blob_sha256'] and ast_id(blob.decode().replace('\r\n','\n'))==g['ref_ast_sha']
    assert seen==cases.keys()
    pred=load(P/'predictions.json');keys=set();assert len(pred)==64
    for r in pred:
        key=r['request_sha'];assert key not in keys;keys.add(key)
        a=r['arm'];j=jobs[r['id'],a];call=json.loads(gzip.decompress((P/'calls'/(key+'.json.gz')).read_bytes()));req=call['request'];raw=call['response'];resp=raw['choices'][0];gs=scored[r['id'],a]
        assert sha(stable(req))==key and req['messages']==j['messages'] and r['answer']==resp['message']['content'].strip() and gs['request_sha']==key
        assert req['max_tokens']==320 and req['temperature']==0 and req['seed']==17112026 and req['cache_prompt']==False
        spec.add(stable({k:v for k,v in req.items() if k!='messages'}))
        for name in ('prompt_tokens','completion_tokens','total_tokens'):native[a][name].append(raw['usage'][name])
        native[a]['memory_tokens'].append(j['packet_tokens']);native[a]['finish'].append(resp['finish_reason']);native[a]['wall_seconds'].append(call['seconds'])
    assert len(spec)==1 and len(list((P/'calls').glob('*.gz')))==64
    digest={a:{'requests':len(v['prompt_tokens']),'sums':{k:sum(ls) for k,ls in v.items() if k!='finish'},'means':{k:statistics.mean(ls) for k,ls in v.items() if k!='finish'},'finish':dict(collections.Counter(v['finish']))} for a,v in native.items()}
    out={'distinct_native_requests':len(keys),'matched_source_snapshot_count':len(cases),'back_end_request':json.loads(next(iter(spec))),'usage':digest,'reader_input_sha256':sha((L/'reader_inputs.json').read_bytes())}
    if '--write-report' in sys.argv:(L/'native_audit.json').write_text(json.dumps(out,indent=1))
    else:assert out==load(L/'native_audit.json')
    print('PASS',out)
if __name__=='__main__':main()
