"""Inventory archived successful native chat completions, including duplicate physical requests."""
import collections
import gzip
import hashlib
import json
from pathlib import Path

BASE=Path(__file__).resolve().parent
GROUPS=('repair/calls','repair/cap1024/calls','concord/calls','concord/highlight/calls','concord/controls/calls','concord/judge/calls','concord/highlight_judge/calls','concord/controls/judge_calls')
def key(v):
    return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def meaning(choice):
    msg=choice['message'];tools=[]
    for c in msg.get('tool_calls') or []:
        fn=c.get('function',{})
        args=fn.get('arguments','')
        try:args=json.loads(args)
        except (ValueError,TypeError):pass
        tools.append([fn.get('name'),args])
    return [msg.get('content'),tools,choice.get('finish_reason')]

def main():
    requests=collections.defaultdict(list)
    groups={};models=collections.Counter()
    for group in GROUPS:
        counted=collections.Counter()
        for path in sorted((BASE/group).glob('*.gz')):
            row=json.loads(gzip.decompress(path.read_bytes()))
            if row.get('code',200)!=200:
                counted['unsuccessful_receipts']+=1
                continue
            req=row['request'];res=row['response']
            assert 'messages' in req and res.get('choices'),(group,path.name)
            use=res['usage'];counted['completed_responses']+=1
            models[req['model']]+=1
            for field in ('prompt_tokens','completion_tokens'):
                counted[field]+=use[field]
            requests[key(req)].append((group,key(meaning(res['choices'][0]))))
        groups[group]=dict(counted)
    duplicates=[v for v in requests.values() if len(v)>1]
    discrepant=[v for v in duplicates if len({s for _,s in v})>1]
    report={'scope':'Archived successful chat completions in the listed physical response directories. Excludes HTTP failures, tokenize/health calls, preparatory probes and author-side model calls. Workspaces or references served from an existing file incur no new call here. Completions with same request payload in separate directories count separately as physical receipts.','per_directory':groups,'model_aliases':dict(models),'total_completed':sum(models.values()),'total_prompt_tokens':sum(v.get('prompt_tokens',0) for v in groups.values()),'total_completion_tokens':sum(v.get('completion_tokens',0) for v in groups.values()),'distinct_payloads':len(requests),'payloads_repeated_physically':len(duplicates),'extra_physical_repeats':sum(len(v)-1 for v in duplicates),'repeated_payloads_with_different_text_tools_or_finish':len(discrepant)}
    dest=BASE/'execution_inventory.json'
    if dest.exists():
        assert json.loads(dest.read_bytes())==report
    else:
        dest.write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('per_directory','scope')},ensure_ascii=False))
if __name__=='__main__':main()
