import sys,time
from collections import Counter
from util import *
sys.path[:0]=[str(BASE/'upstream/bench'),str(BASE/'upstream/src')]
from qa_agent.llm_judge import JUDGE_SYSTEM_PROMPT,build_judge_user_prompt,parse_judge_response
import requests
def main(offline=False):
    lock=read(ROOT/'decision_lock.json')['trials'];assert len(lock)==120
    q={r['id']:r for r in read(BASE/'upstream/bench/pioneer_augmented.json')['hotpotqa']}
    assignments=[];prompts={}
    for name,h in sorted(lock.items()):
        p=ROOT/'trials'/name;check(p,h);r=read(p);task=q[r['id']]
        user=build_judge_user_prompt(question=task['question'],gold_answer=task['answer'],prediction=r['answer'] or '',benchmark='hotpotqa')
        msgs=[{'role':'system','content':JUDGE_SYSTEM_PROMPT},{'role':'user','content':user}];key=digest(encode(msgs));prompts[key]=msgs
        assignments.append(dict(id=r['id'],arm=r['arm'],key=key))
    save(ROOT/'judge_assignments.json.gz',assignments)
    verdict={};refs={};stats=Counter()
    for key,ms in sorted(prompts.items()):
        verdict[key]=None;refs[key]=[]
        for cap in (192,384):
            body=dict(model='qwen38-27b-ud-q4km',messages=ms,temperature=0,seed=18112026,max_tokens=cap,chat_template_kwargs={'enable_thinking':False})
            name=key+'_'+str(cap)+'.json.gz';old=BASE/'judge/calls'/name;own=ROOT/'judge_calls'/name
            p=own if own.exists() or not old.exists() else old
            if not p.exists():
                assert not offline
                for attempt in range(4):
                    try:
                        response=requests.post('http://127.0.0.1:18961/v1/chat/completions',json=body,timeout=140);response.raise_for_status();break
                    except requests.RequestException:
                        if attempt==3:raise
                        time.sleep(2**attempt)
                save(p,dict(request=body,response=response.json()))
            rec=read(p);assert rec['request']==body;refs[key].append(dict(file=name,source='controls' if p==own else 'prior',sha256=digest(p.read_bytes())))
            try:v=parse_judge_response(rec['response']['choices'][0]['message'].get('content') or '')
            except ValueError:continue
            verdict[key]=v.correct;break
    save(ROOT/'verdicts.json.gz',verdict);save(ROOT/'judge_receipts.json.gz',refs)
    save(ROOT/'judge_lock.json',{n:digest((ROOT/n).read_bytes()) for n in ('judge_assignments.json.gz','verdicts.json.gz','judge_receipts.json.gz')})
    print('blinded unique inputs',len(prompts),'new judge calls',len(list((ROOT/'judge_calls').glob('*.gz'))),flush=True)
if __name__=='__main__':main('--verify' in sys.argv)

