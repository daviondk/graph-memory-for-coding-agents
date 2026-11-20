"""Re-use the native public R5 files, matching tool output in two independent fields. Static parsing only."""
from pathlib import Path
import concurrent.futures,difflib,gzip,hashlib,json,re,time,urllib.request
from collections import Counter
D=Path(__file__).resolve().parent;W=D.parent/'writer'
def h(data):return hashlib.sha256(data).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def rr(p):
    with gzip.open(p,'rt',encoding='utf8') as f:yield from map(json.loads,f)
def write(f,x):f.write(json.dumps(x,ensure_ascii=True,separators=(',',':'))+'\n')
def save(p,x):(D/p).write_text(json.dumps(x,indent=1,ensure_ascii=True),encoding='utf8')
def stamp():return time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
def text(v):
    return v if isinstance(v,str) else '\n'.join(x['text'] for x in (v or []) if isinstance(x,dict) and isinstance(x.get('text'),str))
def canon(a):return str(a).replace('\r\n','\n').strip()
def normalize_z(s):
    calls=[];m=None
    for x in s['history']:
        if x.get('role')=='assistant':
            m=None
            if 'action' in x:
                m=[canon(x['action']),x.get('tool_calls') or [],[]];calls.append(m)
        elif x.get('role')=='tool' and m is not None:
            m[2].append((x.get('tool_call_ids',[]),text(x.get('content'))))
    return calls
def extract(task,raw):
    s=json.loads(raw);calls=normalize_z(s);steps=s['trajectory']
    assert len(steps)==len(task['events'])
    amap={}
    for lo,hi,n in difflib.SequenceMatcher(a=[canon(z.get('action','')) for z in steps],b=[x[0] for x in calls],autojunk=False).get_matching_blocks():
        for off in range(n):amap[lo+off]=hi+off
    out=[];ct=Counter()
    for i,(ev,step) in enumerate(zip(task['events'],steps)):
        if ev[0]!='other':out.append(None);continue
        ct['opaque']+=1
        if i not in amap:out.append(None);ct['unaligned']+=1;continue
        action,tools,ans=calls[amap[i]]
        if len(tools)!=1 or len(ans)!=1 or ans[0][0]!=[tools[0]['id']]:
            out.append(None);ct['unpaired']+=1;continue
        tool=tools[0]['function'];args=tool['arguments']
        try:args=json.loads(args) if isinstance(args,str) else args
        except (ValueError,TypeError):args={}
        cmd=args.get('command','') if isinstance(args,dict) else ''
        a=step.get('observation','').replace('\r\n','\n').split('\n')
        b=ans[0][1].replace('\r\n','\n').split('\n')
        # Offset for literal commands is the position in raw stdout. We record both boundaries.
        pieces=[[x,y,a[x:x+n]] for x,y,n in difflib.SequenceMatcher(a=a,b=b,autojunk=False).get_matching_blocks() if n]
        ct['paired']+=1;ct['observed_lines']+=sum(len(v) for _,_,v in pieces)
        out.append(dict(name=tool.get('name'),command=cmd,pieces=pieces,raw_length=len(a),shown_length=len(b)))
    return [task['instance'],out],ct
def main():
    rec={r['id']:r for r in read(W/'receipts.json')};tasks=[t for i in range(8) for t in rr(W/f'source_{i}.jsonl.gz')]
    save('source_lock.json',dict(utc=stamp(),protocol=h((D/'PROTOCOL.md').read_bytes()),receipts=h((W/'receipts.json').read_bytes()),fetch=h(Path(__file__).read_bytes()),n=len(tasks)))
    def one(task):
        id=task['instance'];r=rec[id]
        for attempt in range(3):
            try:
                with urllib.request.urlopen(r['url'],timeout=40) as f:raw=f.read(48*1024**2+1)
                assert h(raw)==r['sha256'];result,ct=extract(task,raw)
                return result,dict(id=id,sha=r['sha256'],size=len(raw),counts=dict(ct))
            except (OSError,ValueError,KeyError) as e:
                if attempt==2:return [id,[None]*len(task['events'])],dict(id=id,error=str(type(e).__name__))
                time.sleep(.3*(attempt+1))
    records=[]
    with concurrent.futures.ThreadPoolExecutor(12) as pool,gzip.open(D/'raw_pairs.jsonl.gz','wt',encoding='utf8',compresslevel=3) as g:
        for row,receipt in pool.map(one,tasks):
            records.append(receipt);write(g,row)
            if len(records)%16==0:print(len(records),sum('error' in r for r in records),flush=True)
    save('source_receipt.json',dict(utc=stamp(),records=records,pairs=h((D/'raw_pairs.jsonl.gz').read_bytes())))
if __name__=='__main__':main()

