"""Post-E1 strong context-only control; no state between examples, no strings retained."""
import csv,gzip,hashlib,json,random,re,sys
from collections import Counter,defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
from project import project
from fetch import SPLITS
TARGETS={'click','text_input','submit','change'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def actions(text):
    pos=0
    while pos<len(text):
        match=re.search(r'\b([a-z_]+)\(',text[pos:])
        if not match:break
        name=match.group(1);start=pos+match.start();i=pos+match.end();begin=i
        depth=1;quote=None;escape=False
        while i<len(text) and depth:
            ch=text[i]
            if escape:escape=False
            elif ch=='\\':escape=True
            elif quote:
                if ch==quote:quote=None
            elif ch in ('"',"'"):quote=ch
            elif ch=='(':depth+=1
            elif ch==')':depth-=1
            i+=1
        if depth:break
        yield name,text[begin:i-1]
        pos=i
def choose(h,c,editable):
    last=None
    for k,args in actions(h or ''):
        if k=='load' or k in TARGETS:
            m=re.search(r'\buid="([A-Za-z0-9_-]+)"',args)
            last=m.group(1) if k=='click' and m else None
    return last if any(u==last and (b or not editable) for u,t,b in c) else c[0][0] if c else None
def run():
    lock={f:sha(ROOT/f) for f in ('PROTOCOL.md','evaluate.py')}
    (ROOT/'input_lock.json').write_text(json.dumps(lock,indent=1))
    gold={(r['split'],r['demo'],int(r['turn'])):r for r in csv.DictReader((ROOT.parent/'per_action.csv').open(encoding='utf8',newline=''))}
    groups=defaultdict(lambda:defaultdict(Counter));rows=[]
    for split in SPLITS[1:]:
        with gzip.open(ROOT.parent/'raw'/(split+'.json.gz'),'rt',encoding='utf8') as f:
            for line in f:
                src=json.loads(line)
                # Projection reads label for evaluation only; decisions below consume h,c.
                r=project(src);edit=choose(src.get('action_history'),r['c'],True);anyclick=choose(src.get('action_history'),r['c'],False)
                if r['k'] not in TARGETS or not r['y']:continue
                key=(split,r['demo'],r['turn']);prior=gold[key];assert r['y']==prior['target']
                memory=prior['last_click_editable'];base=prior['released']
                obs={'n':1,'context_editable':int(edit==r['y']),'context_anyclick':int(anyclick==r['y']),'memory':int(memory==r['y']),'released':int(base==r['y']),'different':int(edit!=memory)}
                obs.update({'W':int(obs['memory']>obs['context_editable']),'L':int(obs['memory']<obs['context_editable'])})
                for s in (split,'pooled'):groups[s][r['demo']].update(obs)
                rows.append({'s':split,'d':r['demo'],'i':r['turn'],'p':edit,'p_any':anyclick,'y':r['y'],'prior':memory})
    result={}
    for s,ds in groups.items():
        total=Counter()
        for d,c in ds.items():total.update(c)
        pairs=[(c['memory']-c['context_editable'],c['n']) for c in ds.values()];rng=random.Random(17112026);stats=[]
        for _ in range(2000):
            samp=rng.choices(pairs,k=len(pairs));stats.append(sum(x for x,n in samp)/sum(n for x,n in samp))
        stats.sort();result[s]={**dict(total),'demos':len(ds),'delta_memory_minus_context':(total['memory']-total['context_editable'])/total['n'],'ci95':[stats[49],stats[1949]]}
    with (ROOT/'predictions.jsonl.gz').open('wb') as fp,gzip.GzipFile(fileobj=fp,mode='wb',mtime=0,filename='') as f:
        for r in rows:f.write((json.dumps(r,separators=(',',':'))+'\n').encode())
    (ROOT/'results.json').write_text(json.dumps(result,indent=1))
    (ROOT/'output_lock.json').write_text(json.dumps({f:sha(ROOT/f) for f in ('predictions.jsonl.gz','results.json')},indent=1))
    print(result)
if __name__=='__main__':run()

