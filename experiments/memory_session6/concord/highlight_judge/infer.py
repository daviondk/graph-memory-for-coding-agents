import importlib.util
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent
CONCORD=ROOT.parent
spec=importlib.util.spec_from_file_location('registered_judge',CONCORD/'judge/infer.py')
judge=importlib.util.module_from_spec(spec)
spec.loader.exec_module(judge)
import requests

def main():
    answers=judge.read(CONCORD/'highlight/answers_for_judge.json')
    assert len(answers)==80 and len({(r['id'],r['arm']) for r in answers})==80
    cases={r['id']:r for r in judge.read(CONCORD/'upstream/bench/pioneer_augmented.json')['hotpotqa']}
    prompts={};rows=[]
    for r in answers:
        q=cases[r['id']]
        user=judge.build_judge_user_prompt(question=q['question'],gold_answer=q['answer'],prediction=r['answer'] or '',benchmark='hotpotqa')
        msg=[{'role':'system','content':judge.JUDGE_SYSTEM_PROMPT},{'role':'user','content':user}]
        key=judge.digest(judge.encode(msg))
        prompts[key]=msg
        rows.append(dict(id=r['id'],arm=r['arm'],key=key))
    judge.freeze(ROOT/'assignments.json.gz',rows)
    judge.freeze(ROOT/'input_lock.json',{'protocol':judge.digest((ROOT/'PROTOCOL.md').read_bytes()),'answers':judge.digest((CONCORD/'highlight/answers_for_judge.json').read_bytes()),'implementation':judge.digest(Path(__file__).read_bytes()),'parent_protocol':judge.digest((CONCORD/'judge/PROTOCOL.md').read_bytes())})
    folder=ROOT/'calls';folder.mkdir(exist_ok=True)
    verdicts={};assets={}
    for key,messages in sorted(prompts.items()):
        for cap in (192,384):
            name=key+'_'+str(cap)+'.json.gz'
            baseline=CONCORD/'judge/calls'/name
            path=baseline if baseline.exists() else folder/name
            data=dict(model='qwen38-27b-ud-q4km',messages=messages,temperature=0,seed=18112026,max_tokens=cap,chat_template_kwargs={'enable_thinking':False})
            if not path.exists():
                if '--verify' in sys.argv: raise FileNotFoundError(path)
                result=requests.post('http://127.0.0.1:18961/v1/chat/completions',json=data,timeout=100)
                result.raise_for_status()
                judge.freeze(path,{'request':data,'response':result.json()})
            rec=judge.read(path)
            assert rec['request']==data
            assets[path.relative_to(CONCORD).as_posix()]=judge.digest(path.read_bytes())
            try:
                ans=judge.parse_judge_response(rec['response']['choices'][0]['message']['content'] or '')
            except ValueError:
                continue
            verdicts[key]=ans.correct
            break
        else:
            verdicts[key]=None
    judge.freeze(ROOT/'decision_lock.json',assets)
    judge.freeze(ROOT/'verdicts.json.gz',verdicts)
    print('cases',len(rows),'distinct prompts',len(prompts),'previous receipts',sum(k.startswith('judge/') for k in assets),'new receipts',sum(k.startswith('highlight_judge/') for k in assets))

if __name__=='__main__':
    main()
