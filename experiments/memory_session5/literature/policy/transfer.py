"""Execute original last-N observation masking and score bounded supplementary memories."""
from __future__ import annotations
import ast,collections,gzip,hashlib,json,random,re,shutil,sys
from pathlib import Path
from typing import Literal
ROOT=Path(__file__).resolve().parent
ALLOW=set('pandas-dev__pandas dask__dask scanny__python-pptx pygments__pygments lincolnloop__python-qrcode jaraco__inflect un33k__python-slugify matthewwithanm__python-markdownify HIPS__autograd mozillazg__python-pinyin pydata__patsy seatgeek__thefuzz tkrajina__gpxpy dbader__schedule'.split())
TOOLS={'str_replace_editor','str_replace_based_edit_tool','edit_file'}
LINE=re.compile(r'^ *(\d+)\t(.*)$')
def save(path,data):
    b=json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    path.write_bytes(gzip.compress(b,mtime=0) if path.suffix=='.gz' else b)
def load(path):return json.loads(gzip.decompress(path.read_bytes()) if path.suffix=='.gz' else path.read_bytes())
def chunks(s):
    out=[];group=[]
    for l in s.replace('\r\n','\n').split('\n'):
        m=LINE.fullmatch(l)
        if not m:continue
        n=int(m[1])
        if group and n!=group[-1][0]+1:out.append(group);group=[]
        group.append([n,m[2]])
    if group:out.append(group)
    return out
def project():
    base=ROOT.parents[2]/'memory_session4/compact'
    out=[];manifest=[]
    for src in [base/'source',base/'tagged/source']:
        for f in sorted(src.glob('*.jsonl.gz')):
            manifest.append({'source':str(f.relative_to(base)),'sha256':hashlib.sha256(f.read_bytes()).hexdigest()})
            for line in gzip.open(f,'rt',encoding='utf8'):
                r=json.loads(line)
                if r['instance'].split('.')[0] not in ALLOW or not r['events']:continue
                if re.search(r'\b(CVE-\d|vulnerabilit|exploit|malware|sql injection|remote code execution|path traversal)',r['issue'],re.I):continue
                events=[]
                for name,a,obs in r['events']:
                    if name not in TOOLS or not isinstance(a,dict):events.append(None);continue
                    path=a.get('path','').removeprefix('/testbed/').removeprefix('./')
                    if not path or path.startswith('/') or '..' in path.split('/'):events.append(None);continue
                    cmd=a.get('command')
                    arg={k:v for k,v in a.items() if k in ('old_str','new_str','file_text') and isinstance(v,str)}
                    success=cmd=='str_replace' and bool(re.search(r'The file .*? has been edited\.|successfully replaced',obs[:1300],re.I))
                    events.append([path,cmd,arg,chunks(obs),success])
                out.append([r['traj'],r['instance'],events])
    shutil.copyfile(base/'source/qwen_tokenizer.json',ROOT/'tokenizer.json')
    save(ROOT/'transfer_inputs.json.gz',out);save(ROOT/'transfer_inputs_manifest.json',manifest)
def original():
    from pydantic import BaseModel,ConfigDict,field_validator
    path=ROOT/'sources/history_processors.py';raw=path.read_text(encoding='utf8')
    tree=ast.parse(raw)
    names={'_get_content_text','_set_content_text','LastNObservations'}
    nodes=[x for x in tree.body if getattr(x,'name',None) in names]
    assert len(nodes)==3
    ns=dict(BaseModel=BaseModel,ConfigDict=ConfigDict,field_validator=field_validator,History=list,HistoryItem=dict,Literal=Literal)
    mod=compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec',dont_inherit=True)
    exec(mod,ns)
    return ns['LastNObservations'](n=10,polling=1)
def get(goal,t):
    for ev in goal[t:t+4]:
        if ev and ev[1]=='str_replace' and ev[2].get('old_str'):
            return ev if ev[4] else None
    return None
def contains(blocks,p,t):return any(t in b for b in blocks.get(p,[]))
def choose(blocks,side,tokenizer,dedup,cache):
    selected=collections.defaultdict(list);lines=[];lastcost=0
    for p,start,end,body in blocks:
        if dedup and contains(side,p,body):continue
        key=(p,start,end,body)
        if key not in cache:
            wire=f'@@ {p} {start}..{end} @@\n'+body
            cache[key]=(wire,len(tokenizer.encode(wire,add_special_tokens=False).ids))
        wire,size=cache[key]
        if size>260 or size+lastcost>260:continue
        w='\n'.join(lines+[wire]);cost=len(tokenizer.encode(w,add_special_tokens=False).ids)
        if cost<=256:
            selected[p].append(body);lines.append(wire);lastcost=cost
    return selected,lastcost
def run():
    from tokenizers import Tokenizer
    tok=Tokenizer.from_file(str(ROOT/'tokenizer.json'));policy=original();rows=[];data=load(ROOT/'transfer_inputs.json.gz')
    for tr,i,events in data:
        cache={};history=[{'message_type':'observation','role':'user','content':'Task'}]
        for j,ev in enumerate(events,1):
            history.extend([{'role':'assistant','message_type':'action','content':'A'+str(j)},
                           {'role':'user','message_type':'observation','content':'O'+str(j)}])
            if j%4 or j==len(events):continue
            # The original processor depends on message types/tags and order. Stable unique tokens identify retained candidates.
            new=policy(history);seen={int(v['content'][1:]) for v in new if v['message_type']=='observation' and v['content'].startswith('O') and v['content'][1:].isdigit()}
            assert seen==set(range(max(1,j-9),j+1))
            assert all(new[k]==history[k] for k in range(1,len(history),2))
            target=get(events,j)
            if not target:continue
            path,_,a,_,_=target;old=a['old_str'];observed=collections.defaultdict(list);prior_args=collections.defaultdict(list);arch=[];allobs=collections.defaultdict(list)
            for k,e in enumerate(events[:j],1):
                if not e:continue
                p,_,args,groups,_=e
                prior_args[p].extend(v for v in args.values() if v)
                for group in groups:
                    text='\n'.join(x[1] for x in group);allobs[p].append(text)
                    if k in seen:observed[p].append(text)
                    else:
                        for pos in range(0,len(group),8):
                            part=group[pos:pos+8]
                            arch.append((p,part[0][0],part[-1][0],'\n'.join(v for n,v in part)))
            side={p:observed[p]+prior_args[p] for p in set(observed)|set(prior_args)}
            output={'id':i,'traj':tr,'cut':j,'obs':contains(observed,path,old),'args':contains(prior_args,path,old),'available':contains(side,path,old),'all_obs':contains(allobs,path,old)}
            for name,dedup in [('raw',False),('dedup',True)]:
                context,cost=choose(reversed(arch),side,tok,dedup,cache)
                output[name]=output['available'] or contains(context,path,old)
                output[name+'_cost']=cost
            rows.append(output)
    save(ROOT/'transfer_rows.json.gz',rows)
    return rows
def summarize(rows):
    result={}
    for name,subset in [('all',rows),('active',[r for r in rows if r['cut']>10])]:
        totals={k:sum(r[k] for r in subset) for k in ('obs','args','available','all_obs','raw','dedup','raw_cost','dedup_cost')}
        groups=collections.defaultdict(list)
        for r in subset:groups[r['id']].append(r)
        contrasts={}
        for tr,ctrl in [('available','obs'),('dedup','raw'),('dedup','available')]:
            effects=[(sum(int(r[tr])-int(r[ctrl]) for r in g),len(g)) for g in groups.values()]
            rr=random.Random(51711);boot=[]
            for _ in range(3000):
                samp=rr.choices(effects,k=len(effects));boot.append(sum(e for e,n in samp)/sum(n for e,n in samp))
            boot.sort();win=sum(r[tr] and not r[ctrl] for r in subset);loss=sum(r[ctrl] and not r[tr] for r in subset)
            contrasts[tr+'-'+ctrl]={'win':win,'loss':loss,'ci95':[boot[74],boot[2924]]}
        result[name]={'n':len(subset),'issues':len(groups),'trajectories':len(set(r['traj'] for r in subset)),'sum':totals,'contrasts':contrasts}
    return result
def main():
    if '--project' in sys.argv:project()
    rows=run();result=summarize(rows);save(ROOT/'transfer_results.json',result);print(json.dumps(result,indent=1))
if __name__=='__main__':main()
