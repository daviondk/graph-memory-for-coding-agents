"""Descriptive audit. Python 3.10+. Uses only the standard library and public traces."""
import hashlib, json, re, shlex, time
from pathlib import Path
from urllib.request import urlopen, Request
from collections import defaultdict, Counter
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

REV = '11164976b4f920cdb0d0cd570ca572e49acea1e8'
REPO = 'Tongyi-ConvAI/VibeMemBench'
SEED = 'memory-review-20261116/v1'
def get(url):
    for attempt in range(3):
        try:
            with urlopen(Request(url,headers={'User-Agent':'memory-literature-review/1'}),timeout=30) as response:
                return json.load(response)
        except Exception:
            if attempt == 2: raise
            time.sleep(1+attempt)
def order(x): return hashlib.sha256((SEED+'|'+x).encode()).hexdigest()
def parse(command, wrapped=False):
    # Optional single cd. Retain cwd as part of the signature; no pipes, command chains or expansion.
    if wrapped:
        command=re.sub(r'\s*\|\s*(?:tail|head)\s+(?:-n\s+|-)[1-9]\d*\s*$', '', command)
        command=re.sub(r'\s+2>&1\s*$', '', command)
    match=re.fullmatch(r'\s*(?:cd\s+([\w./-]+)\s*&&\s*)?((?:python(?:3)?\s+-m\s+)?pytest(?:\s+[^\n]+)?)\s*',command)
    if not match: return
    body=match[2]
    if re.search(r'[;&|<>`$()\\\n]',body): return
    try: tokens=shlex.split(body)
    except ValueError: return
    return (match[1] or '[default]')+' :: '+shlex.join(tokens)
def one(path):
    u='https://huggingface.co/datasets/'+REPO+'/resolve/'+REV+'/'+quote(path)
    d=get(u)
    cmds={}
    events=[]
    for msg in d['messages']:
        for c in msg.get('tool_calls') or []:
            if c.get('function',{}).get('name') != 'bash':continue
            try: cmd=json.loads(c['function']['arguments'])['command']
            except (ValueError,KeyError,TypeError):continue
            key=parse(cmd,wrapped=True)
            if key:cmds[c['id']]=(key, parse(cmd) is not None)
        if msg.get('role')!='tool' or msg.get('tool_call_id') not in cmds:continue
        extra=msg.get('extra') or {}
        rc=extra.get('returncode')
        out=extra.get('raw_output') or msg.get('content','')
        # Count asserted pass or test failure, not merely a nonzero command or collection error.
        # Never interpret the exit code of tail/head as the exit code of pytest.
        lines=[line.strip(' =\t\r') for line in out.splitlines()]
        summaries=[ln for ln in lines if re.match(r'^\d+ (passed|failed|errors?|skipped|deselected|xfailed|warnings?)\b',ln) and re.search(r'\bin \d+(?:\.\d+)?s\b',ln)]
        summary=summaries[-1] if summaries else ''
        status='other'
        if re.search(r'\b[1-9]\d* failed\b',summary): status='failed'
        elif re.search(r'\b[1-9]\d* passed\b',summary) and not re.search(r'\b[1-9]\d* errors?\b',summary):status='passed'
        key,strict=cmds[msg['tool_call_id']]
        events.append({'cmd':key,'strict':strict,'result':status,'summary':summary[:220]})
    return {'path':path,'repo':path.split('/')[2],'events':events}
def main():
    api='https://huggingface.co/api/datasets/'+REPO+'/revision/'+REV
    data=get(api)
    groups=defaultdict(list)
    for file in data['siblings']:
        p=file['rfilename']
        if p.startswith('history/python/') and p.endswith('.traj.json'): groups[p.split('/')[2]].append(p)
    eligible=[k for k in groups if len(groups[k])>=8]
    selected=sorted(eligible,key=order)[:8]
    paths=[p for k in selected for p in sorted(groups[k],key=order)[:8]]
    with ThreadPoolExecutor(max_workers=6) as pool:
        traces=list(pool.map(one,paths))
    by=defaultdict(list)
    for t in traces:
        for ev in t['events']:by[t['repo'],ev['cmd']].append((t['path'],ev['result']))
    repeated={k:v for k,v in by.items() if len({p for p,s in v})>=2}
    both={k:v for k,v in repeated.items() if any(pa!=pb and sa=='passed' and sb=='failed' for pa,sa in v for pb,sb in v)}
    out={'source_revision':REV,'seed':SEED,'eligible_repos':len(eligible),'traces':traces,
         'counts':{'repos':len(selected),'traces':len(traces),'traces_with_pytest':sum(bool(t['events']) for t in traces),
                   'traces_with_interpretable_pytest':sum(any(e['result']!='other' for e in t['events']) for t in traces),
                   'strict_events':sum(e['strict'] for t in traces for e in t['events']),'events':sum(len(t['events']) for t in traces),'outcomes':dict(Counter(e['result'] for t in traces for e in t['events'])),
                   'unique_commands_within_repo':len(by),'repeated_across_traces':len(repeated),'opposite_results_across_traces':len(both)},
         'opposite_signatures':[[*k,v] for k,v in both.items()]}
    print(json.dumps(out,ensure_ascii=True,indent=2))
if __name__=='__main__':main()

