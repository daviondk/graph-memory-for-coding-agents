"""Independent offline reconstruction of all semantic labels from actor answers and native judge receipts."""
import ast
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
BASE=HERE.parent
def load(path):
    blob=path.read_bytes()
    return json.loads(gzip.decompress(blob) if path.suffix=='.gz' else blob)

def digest(msg):
    return hashlib.sha256(json.dumps(msg,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def parse(text):
    candidates=[text.strip()]
    fence=re.search(r'```(?:json)?\s*(.*?)\s*```',text,flags=re.DOTALL|re.IGNORECASE)
    if fence:candidates.insert(0,fence[1].strip())
    for cand in candidates:
        try:obj=json.loads(cand)
        except ValueError:continue
        if isinstance(obj,dict) and 'correct' in obj:
            return bool(obj['correct']),type(obj['correct']).__name__
    return None,None

def main():
    parent=load(HERE/'input_lock.json')
    source=BASE/'upstream/bench/qa_agent/llm_judge.py'
    assert hashlib.sha256(source.read_bytes()).hexdigest()==parent['grader']
    mod=ast.parse(source.read_text(encoding='utf8'))
    system=next(ast.literal_eval(node.value) for node in mod.body if isinstance(node,ast.Assign) and getattr(node.targets[0],'id',None)=='JUDGE_SYSTEM_PROMPT')
    roster={r['id']:r for r in load(BASE/'upstream/bench/pioneer_augmented.json')['hotpotqa']}
    original=load(BASE/'published_projection.json.gz')
    answers={('released',r['actor'],r['arm'],r['id']):r['answer'] for r in original}
    for r in load(BASE/'local_projection.json.gz'):
        answers['local','qwen38-27b-ud-q4km',r['arm'],r['id']]=r['answer']
    for r in load(BASE/'highlight/answers_for_judge.json'):
        answers['local','qwen38-27b-ud-q4km',r['arm'],r['id']]=r['answer']
    assert len(answers)==800
    indicators=Counter()
    for folder in [HERE,BASE/'highlight_judge']:
        calls=load(folder/'decision_lock.json')
        registered=load(folder/'verdicts.json.gz')
        rows=load(folder/'assignments.json.gz')
        by_key={}
        for name,sha in calls.items():
            path=(folder/'calls' if folder==HERE else BASE)/name
            assert hashlib.sha256(path.read_bytes()).hexdigest()==sha
            key=path.name.split('_')[0]
            r=load(path)
            assert digest(r['request']['messages'])==key
            req=r['request'];assert req['model']=='qwen38-27b-ud-q4km' and req['temperature']==0 and req['chat_template_kwargs']=={'enable_thinking':False}
            assert req['max_tokens'] in (192,384) and req['seed']==18112026
            assert req['messages'][0]=={'role':'system','content':system}
            by_key.setdefault(key,{})[req['max_tokens']]=parse(r['response']['choices'][0]['message'].get('content') or '')
        for key,trials in by_key.items():
            label,kind=trials[192]
            if label is None:label,kind=trials[384]
            else:assert 384 not in trials
            assert label==registered[key]
            indicators[str(kind)]+=1
        assert set(by_key)==set(registered)
        for row in rows:
            tid=row['id'];task=roster[tid]
            a=answers[row.get('source','local'),row.get('actor','qwen38-27b-ud-q4km'),row['arm'],tid] or ''
            user='Benchmark: hotpotqa\nQuestion:\n'+task['question'].strip()+'\n\nGold answer:\n'+task['answer'].strip()+'\n\nModel prediction:\n'+(a.strip() or '(empty)')+'\n'
            assert digest([{'role':'system','content':system},{'role':'user','content':user}])==row['key']
    print('PASS raw blind scorer, every official prompt and answer mapping, 800 arm-case records;',dict(indicators))
if __name__=='__main__':main()
