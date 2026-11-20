"""The planner has no read path to any evaluation trajectory, hidden label or environment state."""
import json,hashlib,re,time,collections
from urllib.request import Request,urlopen
from pathlib import Path
from policy import goals,kind
ROOT=Path(__file__).resolve().parent
def h(x):return hashlib.sha256(x.encode()).hexdigest()
def enc(x):return json.dumps(x,ensure_ascii=True,sort_keys=True,separators=(',',':'))
def save(p,x):
    tmp=p.with_suffix('.tmp'); tmp.write_text(json.dumps(x,indent=1));tmp.replace(p)
SYSTEM=('You are the search planner for an embodied household agent. Rank all allowed receptacle classes by where the named item is likely to be found in this unfamiliar room. If past examinations are supplied, consider both sightings and how often locations were examined. Use ordinary world knowledge too. Reply only with a JSON array of class strings, most likely first. Include each allowed class exactly once.')
def plan(target,locations,arm,m):
    actual_target=target
    if arm=='q_placebo':
        donors=sorted(k for k in m['hits'] if k!=target)
        actual_target=donors[int(h('unrelated|'+target),16)%len(donors)]
    message='Target: '+target+'\nAllowed locations: '+', '.join(locations)
    if arm!='q_prior':
        message+='\nPrior household search observations for this target (location: present / examined):\n'+'\n'.join(f"{c}: {m['hits'].get(actual_target,{}).get(c,0)} / {m['seen'].get(c,0)}" for c in locations)
    payload={'model':'qwen38-27b-ud-q4km','messages':[{'role':'system','content':SYSTEM},{'role':'user','content':message}],'temperature':0,'seed':17112026,'max_tokens':256,'stream':False}
    key=h(enc(payload));path=ROOT/'planner_calls'/(key+'.json')
    if not path.is_file():
        req=Request('http://127.0.0.1:18839/replicate/0/v1/chat/completions',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
        start=time.monotonic()
        with urlopen(req,timeout=240) as reply:response=json.load(reply)
        save(path,{'request':payload,'response':response,'seconds':time.monotonic()-start})
    raw=json.loads(path.read_bytes())['response']['choices'][0]['message']['content']
    tokens=re.findall(r'[a-z]+',raw.lower());order=list(dict.fromkeys(t for t in tokens if t in locations))
    return {'key':key,'rank':order+[c for c in locations if c not in order],'missing':len(locations)-len(order),'evidence_source':None if arm=='q_prior' else actual_target}
def main():
    roster=json.loads((ROOT/'initial.json').read_bytes());m=json.loads((ROOT/'learned.json').read_bytes());out={}; (ROOT/'planner_calls').mkdir(exist_ok=True)
    jobs={}
    for r in roster:
        obj,dst,op,_=goals(r['observation']);ls=sorted({kind(c[6:]) for c in r['commands'] if c.startswith('go to ')})
        for t in ([obj,dst] if op=='light' else [obj]):
            for arm in ('q_prior','q_shown','q_placebo'):
                if not t:continue
                key=enc([t,ls,arm]);jobs[key]=(t,ls,arm)
    originals=['PLANNER_PROTOCOL.md','public_init.py','plan.py','planner_roll.py','policy.py','engine.py','initial.json','learned.json','lock.json']
    def lock(paths):return {k:hashlib.sha256((ROOT/k).read_bytes()).hexdigest() for k in paths}
    frozen=ROOT/'planner_input_lock.json'
    if frozen.exists():assert json.loads(frozen.read_bytes())==lock(originals)
    else:save(frozen,lock(originals))
    print('unique planning assignments',len(jobs),flush=True)
    for key in sorted(jobs,key=lambda k:h('s3-plan|'+k)):
        t,ls,arm=jobs[key];out[key]=plan(t,ls,arm,m);save(ROOT/'plans.partial.json',out)
    save(ROOT/'plans.json',out)
    save(ROOT/'planner_lock.json',lock(['planner_input_lock.json','plans.json']+sorted({'planner_calls/'+v['key']+'.json' for v in out.values()})))
    print('native calls',len(set(v['key'] for v in out.values())),flush=True)
if __name__=='__main__':main()
