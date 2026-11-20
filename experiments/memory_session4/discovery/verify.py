"""Offline full scorer reproduction, independent simple policy implementation and lock audit."""
import collections,csv,gzip,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from memory import load_rows,train,State,suggest,TARGETS
from fetch import SPLITS
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def check_lock(base,name):
    obj=json.loads((base/name).read_bytes());obj=obj.get('files',obj)
    for n,h in obj.items():assert digest(base/n)==h,(base,n)
def read_lines(path):
    with gzip.open(path,'rt',encoding='utf8') as f:return [json.loads(l) for l in f]
def main():
    for n in ('input_lock.json','output_lock.json'):check_lock(ROOT,n)
    for folder in ('grounded','context_only'):
        for n in ('input_lock.json','output_lock.json'):check_lock(ROOT/folder,n)
    check_lock(ROOT/'context_only','projection_lock.json')
    tab=train(load_rows('train'));assert tab==json.loads((ROOT/'trained_tables.json').read_bytes())
    predictions=iter(read_lines(ROOT/'predictions.jsonl.gz'))
    visible=read_lines(ROOT/'context_only/history_actions.jsonl.gz')
    visible={(r['s'],r['d'],r['i']):r['actions'] for r in visible}
    cp=read_lines(ROOT/'context_only/predictions.jsonl.gz')
    cp={(r['s'],r['d'],r['i']):r for r in cp}
    demos=set(load_rows('train'));turns=0;targets=0;simple_verified=0;context_verified=0;sets={}
    for s in SPLITS[1:]:
        ds=load_rows(s);assert not demos.intersection(ds),(s,'overlap');demos.update(ds);sets[s]=len(ds)
        for d,rows in ds.items():
            st=State();last_uid=None;was_editable=False;last_kind=None
            for r in rows:
                q=next(predictions);assert (s,d,r['turn'])==(q['s'],q['d'],q['i'])
                preds=suggest(st,r['turn'],r['c'],r['lex'],tab);assert preds==q['pred']
                candidates={u:b for u,t,b in r['c']};fallback=r['c'][0][0] if r['c'] else None
                simple=last_uid if last_kind=='click' and was_editable and last_uid in candidates else fallback
                assert simple==q['pred']['last_click_editable'];simple_verified+=1
                if r['k'] in TARGETS and r['y']:
                    targets+=1;key=(s,d,r['turn']);seq=visible[key];last=seq[-1] if seq else [None,None]
                    c=cp[key];expected=last[1] if last[0]=='click' and candidates.get(last[1],False) else fallback
                    expected_any=last[1] if last[0]=='click' and last[1] in candidates else fallback
                    assert c['p']==expected and c['p_any']==expected_any and c['y']==r['y'] and (c['prior'] or None)==simple
                    context_verified+=1
                if r['k']=='load':last_uid=None;was_editable=False;last_kind=None
                elif r['k'] in TARGETS:
                    last_uid=r['y'];was_editable=candidates.get(last_uid,False);last_kind=r['k']
                st.observe(r['turn'],r['c'],r['k'],r['y']);turns+=1
    assert next(predictions,None) is None
    for f in ('metrics.py','grounded/metrics.py'):
        subprocess.run([sys.executable,str(ROOT/f),'--verify'],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
    out={'passed':True,'heldout_turns_replayed':turns,'identified_targets':targets,'independent_simple_predictions':simple_verified,'independent_context_predictions':context_verified,'demos_per_split':sets,'calibration_retrained_identically':True,'raw_not_required':True}
    (ROOT/'verification.json').write_text(json.dumps(out,indent=1))
    print(json.dumps(out,indent=1))
if __name__=='__main__':main()

