"""Standalone one-action grader; never executes source code. All generated code is treated as text."""
import ast,collections,gzip,hashlib,json,random,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
L=ROOT/'live'
def sha(b):return hashlib.sha256(b).hexdigest()
def ast_id(text):
    try:tree=ast.parse(text)
    except (SyntaxError,ValueError,OverflowError,RecursionError):return None
    return sha(ast.dump(tree,include_attributes=False).encode())
def strict_json(answer):
    try:obj=json.loads(answer)
    except (TypeError,ValueError):return None
    return obj if isinstance(obj,dict) else None
def grade(reply,g,scratch):
    source=gzip.decompress((L/'snapshots'/g['snapshot']).read_bytes()).decode('utf8')
    assert ast_id(source)==g['pre_ast_sha']
    ref=g['ref_ast_sha'];rec={'json_valid':False,'has_action':False,'unique':False,'ast_change':False,'ast_preserves_reference':False,'exact_reference_repair':False,'exact_history':False,'history_eligible':False,'ref_eligible':bool(ref and ref!=g['pre_ast_sha']),'ref_pre_equal':bool(ref and ref==g['pre_ast_sha']),'new_ast_sha':None,'old_count':None,'failure':'malformed_json'}
    h=g['historical'];rec['history_eligible']=bool(h and h['accepted'] and h['path']==g['path'])
    obj=strict_json(reply);rec['json_valid']=obj is not None
    if obj is None:return rec
    old=obj.get('old_str');new=obj.get('new_str')
    if not isinstance(old,str) or not old or not isinstance(new,str) or (obj.get('path') not in (None,g['path'],'/testbed/'+g['path'])):
        rec['failure']='no_valid_edit';return rec
    rec['has_action']=True;count=source.count(old);rec['old_count']=count;rec['unique']=count==1
    rec['exact_history']=bool(rec['history_eligible'] and old==h['old_str'] and new==h['new_str'])
    if count!=1:rec['failure']='old_absent' if count==0 else 'old_ambiguous';return rec
    # Keep edits within an ephemeral plain text file; never import, compile to bytecode or execute actor code.
    with tempfile.TemporaryFile(dir=scratch) as f:
        f.write(source.encode());f.seek(0);blob=f.read();assert blob.count(old.encode())==1
        after=blob.replace(old.encode(),new.encode(),1);f.seek(0);f.write(after);f.truncate();f.flush();f.seek(0);verify=f.read();assert verify==after
    rec['post_bytes_sha']=sha(verify)
    aid=ast_id(verify.decode('utf8'));rec['new_ast_sha']=aid
    rec['ast_change']=bool(aid and aid!=g['pre_ast_sha']);rec['ast_preserves_reference']=bool(aid and ref==aid)
    rec['exact_reference_repair']=bool(rec['ref_eligible'] and aid==ref)
    rec['failure']='success' if rec['ast_change'] else 'parse_failed' if aid is None else 'same_ast'
    return rec
def summary(rows):
    by={a:{r['id']:r for r in rows if r['arm']==a} for a in ['joint','rebased_tail']}
    ids=sorted(by['joint']);assert ids==sorted(by['rebased_tail'])
    report={}
    for metric,mask in [('ast_change',None),('unique',None),('has_action',None),('exact_reference_repair','ref_eligible'),('exact_history','history_eligible')]:
        cases=[i for i in ids if mask is None or by['joint'][i][mask]];vals={a:sum(v[i][metric] for i in cases) for a,v in by.items()}
        ds=[int(by['joint'][i][metric])-int(by['rebased_tail'][i][metric]) for i in cases]
        clusters=collections.defaultdict(list)
        for i,d in zip(cases,ds):clusters[i.split('.')[0]].append(d)
        rng=random.Random(17112026);units=list(clusters.values());cis=[]
        for _ in range(8000):
            s=[d for vs in rng.choices(units,k=len(units)) for d in vs]
            if s:cis.append(sum(s)/len(s))
        cis.sort();report[metric]={'n':len(cases),'success':vals,'wins':ds.count(1),'losses':ds.count(-1),'difference':sum(ds)/len(ds) if ds else None,'repo_clusters':len(units),'ci95':[cis[int(len(cis)*.025)],cis[int(len(cis)*.975)]] if cis else None}
    report['failures']={a:dict(collections.Counter(v['failure'] for v in items.values())) for a,items in by.items()}
    report['changes_to_pre_correct']={a:sum(v['ast_change'] and v['ref_pre_equal'] for v in vs.values()) for a,vs in by.items()}
    return report
def main():
    pred_dir=L/'capsule_calls';lock=pred_dir/'prediction_lock.json';assert lock.is_file()
    frozen=json.loads((L/'grader_lock.json').read_bytes());assert all(sha((ROOT/f).read_bytes())==s for f,s in frozen.items())
    inp_lock=json.loads((L/'live_input_lock.json').read_bytes());assert all(sha((ROOT/f).read_bytes())==s for f,s in inp_lock.items())
    inputs={(r['id'],r['arm']):r for r in json.loads((L/'reader_inputs.json').read_bytes())};pred=json.loads((pred_dir/'predictions.json').read_bytes());assert len(pred)==len(inputs)==64
    gold={v['id']:v for v in json.loads((L/'outcomes.json').read_bytes())};out=[];scratch=ROOT/'live'/'scratch';scratch.mkdir(exist_ok=True)
    assert len({(r['id'],r['arm']) for r in pred})==len(inputs);usage=collections.Counter()
    for r in pred:
        g=gold[r['id']];record=grade(r['answer'],g,scratch);record.update(id=r['id'],arm=r['arm'],request_sha=r['request_sha']);out.append(record)
    results=summary(out);results['identical_messages_pairs']=sum(inputs[i,'joint']['messages']==inputs[i,'rebased_tail']['messages'] for i in gold)
    if '--verify' in sys.argv:
        assert out==json.loads((L/'actions_scored.json').read_bytes());assert results==json.loads((L/'results.json').read_bytes());print('PASS 64 actions, source hashes, prediction linkage and paired metrics')
    else:
        (L/'actions_scored.json').write_text(json.dumps(out,indent=1));(L/'results.json').write_text(json.dumps(results,indent=1))
        print(json.dumps(results,ensure_ascii=True))
if __name__=='__main__':main()
