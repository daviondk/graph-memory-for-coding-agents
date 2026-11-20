"""Blind pooled second-judge pass using the authors' original prompt and parser."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys

import requests

ROOT = Path(__file__).resolve().parent
CONCORD = ROOT.parent
sys.path[:0] = [str(CONCORD / 'upstream/bench'), str(CONCORD / 'upstream/src')]
from qa_agent.llm_judge import JUDGE_SYSTEM_PROMPT, build_judge_user_prompt, parse_judge_response

def encode(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()

def digest(value):
    return hashlib.sha256(value).hexdigest()

def read(path):
    data = path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix == '.gz' else data)

def freeze(path, value):
    if path.exists():
        assert read(path) == value, path
        return
    data = encode(value)
    temp = path.with_suffix('.tmp')
    temp.write_bytes(gzip.compress(data, mtime=0) if path.suffix == '.gz' else data)
    temp.replace(path)

def assemble():
    lock = read(CONCORD / 'decision_lock.json')
    assert len(lock) == 120
    questions = {row['id']: row for row in read(CONCORD / 'upstream/bench/pioneer_augmented.json')['hotpotqa']}
    public = read(CONCORD / 'published_projection.json.gz')
    rows = [('released', r['actor'], r['arm'], r['id'], r['answer']) for r in public]
    for name, expected in sorted(lock.items()):
        path = CONCORD / 'trials' / name
        assert digest(path.read_bytes()) == expected
        r = read(path)
        rows.append(('local', 'qwen38-27b-ud-q4km', r['arm'], r['id'], r['answer']))
    assignments = []
    prompts = {}
    for src, actor, arm, tid, answer in rows:
        task = questions[tid]
        user = build_judge_user_prompt(question=task['question'], gold_answer=task['answer'], prediction=answer or '', benchmark='hotpotqa')
        messages = [{'role': 'system', 'content': JUDGE_SYSTEM_PROMPT}, {'role': 'user', 'content': user}]
        key = digest(encode(messages))
        assignments.append(dict(source=src, actor=actor, arm=arm, id=tid, key=key))
        prompts[key] = messages
    assert len(assignments) == 720
    freeze(ROOT/'assignments.json.gz', assignments)
    freeze(ROOT/'input_lock.json', {'protocol': digest((ROOT/'PROTOCOL.md').read_bytes()), 'native_actor_lock': digest((CONCORD/'decision_lock.json').read_bytes()), 'assignments': digest((ROOT/'assignments.json.gz').read_bytes()), 'grader': digest((CONCORD/'upstream/bench/qa_agent/llm_judge.py').read_bytes()), 'implementation': digest(Path(__file__).read_bytes()), 'n_unique':len(prompts)})
    return prompts

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--verify',action='store_true')
    args=parser.parse_args()
    cache=ROOT/'calls'
    cache.mkdir(exist_ok=True)
    prompts=assemble()
    verdicts={}
    for i,key in enumerate(sorted(prompts)):
        for cap in (192,384):
            request=dict(model='qwen38-27b-ud-q4km',messages=prompts[key],temperature=0,seed=18112026,max_tokens=cap,chat_template_kwargs={'enable_thinking':False})
            path=cache/(key+'_'+str(cap)+'.json.gz')
            if not path.exists():
                if args.verify:
                    raise FileNotFoundError(path)
                response=requests.post('http://127.0.0.1:18961/v1/chat/completions',json=request,timeout=100)
                response.raise_for_status()
                freeze(path,dict(request=request,response=response.json()))
            receipt=read(path)
            assert receipt['request']==request
            text=receipt['response']['choices'][0]['message'].get('content') or ''
            try:
                verdict=parse_judge_response(text)
            except ValueError:
                continue
            verdicts[key]=verdict.correct
            break
        else:
            verdicts[key]=None
        if (i+1)%50==0:
            print('blinded unique verdicts',i+1,'/',len(prompts),flush=True)
    freeze(ROOT/'verdicts.json.gz',verdicts)
    freeze(ROOT/'decision_lock.json',{p.name:digest(p.read_bytes()) for p in sorted(cache.glob('*.gz'))})
    print('completed',len(verdicts),'of which missing',sum(v is None for v in verdicts.values()),flush=True)

if __name__=='__main__':
    main()
