"""Deterministic, bounded read-only observer. It never imports Click or executes issue text."""
from collections import Counter,defaultdict
from math import log
import re,subprocess
from settings import *

def search(pattern,limit):
    proc=subprocess.run(['rg','--no-heading','--with-filename','--line-number','--sort','path','--color','never',
        '--max-count','3','--glob','*.py','--',pattern,'src/click'],cwd=B,capture_output=True)
    assert proc.returncode in (0,1),proc.stderr
    hits=[]
    for s in proc.stdout.decode('utf8').splitlines()[:limit]:
        path,number,line=s.split(':',2)
        hits.append([path.replace('\\','/'),int(number),line])
    return hits

def quote(path,line):
    raw=(B/path).read_bytes();lines=raw.splitlines(keepends=True);i=max(0,line-4)
    for start_line in range(i,-1,-1):
        byte=sum(map(len,lines[:start_line]))
        header=f'[{path} | line {start_line+1} | byte {byte}]\n'
        wanted=UNIT-len(header.encode())-1;fragment=raw[byte:byte+wanted]
        if len(fragment)!=wanted:continue
        try:body=fragment.decode('utf8')
        except UnicodeDecodeError:continue
        rendered=header+body+'\n'
        assert len(rendered.encode())==UNIT
        return dict(path=path,line=start_line+1,byte=byte,length=wanted,body=body,rendered=rendered,sha=h(fragment))
    raise RuntimeError('No equivalent complete UTF-8 source slice')

def words(text):
    return re.findall(r'[a-z][a-z_0-9]+',text.lower())

def main():
    assert sha(ISSUE)==ISSUE_HASH and load(D/'registration.json')['protocol']==sha(D/'PROTOCOL_RU.md')
    actions=[];items=[];seen={};links=set();parent_symbols=defaultdict(set)
    attr=re.compile(r'\b[A-Za-z_]\w*\.([A-Za-z_]\w*)\s*\(')
    definition=re.compile(r'(?m)^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\(')
    def collect(pattern,limit,symbol,parents=()):
        hits=search(pattern,limit);refs=[]
        for path,line_number,line in hits:
            q=quote(path,line_number);tag=q['path'],q['byte']
            if tag not in seen:
                seen[tag]=len(items);q['id']=len(items);items.append(q)
            j=seen[tag];refs.append(j)
            for i in parents:
                if i!=j:links.add((i,j,symbol,'observed search'))
        actions.append(dict(type='search',pattern=pattern,limit=limit,hits=hits,receipts=refs,parents=list(parents)))
    for symbol in ('add_command','default_map'):
        collect(r'^\s*(?:async\s+)?def\s+'+symbol+r'\b',6,symbol)
        collect(r'\b'+symbol+r'\b',6,symbol)
    skip=set('append extend join get items keys values format lower upper split strip replace update setdefault pop add_command default_map'.split())
    for it in items:
        for name in set(attr.findall(it['body']))-skip:parent_symbols[name].add(it['id'])
    for symbol in sorted(parent_symbols,key=lambda s:(-len(parent_symbols[s]),s))[:6]:
        collect(r'^\s*(?:async\s+)?def\s+'+symbol+r'\b',3,symbol,sorted(parent_symbols[symbol]))
    anchors=defaultdict(dict)
    for it in items:
        for m in definition.finditer(it['body']):
            absolute=it['byte']+len(it['body'][:m.start(1)].encode())
            anchors[m[1]].setdefault((it['path'],absolute),set()).add(it['id'])
    for it in items:
        for name in set(attr.findall(it['body'])):
            if len(anchors[name])==1:
                for ids in anchors[name].values():
                    for j in ids:
                        if j!=it['id']:links.add((it['id'],j,name,'observed symbol'))
    n=len(items);terms=[Counter(words(x['body'])) for x in items];query=set(words(ISSUE.read_text(encoding='utf8')))
    avg=sum(sum(m.values()) for m in terms)/n
    df=Counter(w for row in terms for w in row);bm=[]
    for row in terms:
        bm.append(sum(log(1+(n-df[w]+.5)/(df[w]+.5))*2.2*row[w]/(row[w]+1.2*(.25+.75*sum(row.values())/avg)) for w in sorted(query&row.keys())))
    flat=[.8*x/max(max(bm),1e-9)+.2*i/max(1,n-1) for i,x in enumerate(bm)]
    prior=[(x+.01)/(sum(flat)+.01*n) for x in flat];state=prior.copy();neighbors=defaultdict(Counter)
    for i,j,symbol,typ in sorted(links):neighbors[i][j]+=1;neighbors[j][i]+=1
    for _ in range(6):
        nxt=[.3*v for v in prior]
        for i,x in enumerate(state):
            targets=neighbors[i];total=sum(targets.values())
            if not total:nxt[i]+=.7*x
            else:
                for j,w in targets.items():nxt[j]+=.7*x*w/total
        state=nxt
    def select(scores):
        selected=[];order=sorted(range(n),key=lambda i:(-scores[i],i))
        for strict in (True,False):
            for i in order:
                if i in selected:continue
                x=items[i]
                if strict and any(x['path']==items[j]['path'] and
                    min(x['byte']+x['length'],items[j]['byte']+items[j]['length'])-max(x['byte'],items[j]['byte'])>
                    min(x['length'],items[j]['length'])/2 for j in selected):continue
                selected.append(i)
                if len(selected)==min(4,n):return sorted(selected)
        return sorted(selected)
    picked={'flat':select(flat),'graph':select(state),'none':[]}
    for name,ids in picked.items():(P/(name+'.txt')).write_bytes(''.join(items[i]['rendered'] for i in ids).encode())
    assert (P/'flat.txt').stat().st_size==(P/'graph.txt').stat().st_size==UNIT*min(4,n)
    dump(D/'scout.json',dict(actions=actions,items=items,links=sorted(links),scores=dict(flat=flat,graph=state),chosen=picked))
    dump(D/'packet-seal.json',dict(scout=sha(D/'scout.json'),code=sha(D/'scout.py'),registration=sha(D/'registration.json'),
        count=n,searches=len(actions),edges=len(links),shared=len(set(picked['flat'])&set(picked['graph'])),
        packets={name:{'sha':sha(P/(name+'.txt')),'bytes':(P/(name+'.txt')).stat().st_size} for name in picked}))
    print('sealed:',len(actions),'queries',n,'real source receipts',len(links),'edges; common receipts',len(set(picked['flat'])&set(picked['graph'])))
if __name__=='__main__':main()
