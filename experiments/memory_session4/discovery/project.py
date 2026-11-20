"""Privacy-minimal projections. No page text, URLs, user-entered values or utterances are written."""
import gzip,hashlib,json,math,re
from collections import Counter
from pathlib import Path
from fetch import ROOT,SPLITS
UID=re.compile(r'\buid="([A-Za-z0-9_-]+)"')
START=re.compile(r'(?m)(?:^|\n)\(uid = ([A-Za-z0-9_-]+)\)\s*')
TAG=re.compile(r'\[\[tag\]\]\s*(\w+)')
SPEECH=re.compile(r'say\(speaker="instructor", utterance="((?:[^"\\]|\\.)*)"',re.S)
STOP=set('a an the to on please click can you for from and add find it of at i my with is in open want'.split())
def words(text):return [w for w in re.findall(r'[a-z0-9]+',text.lower()) if len(w)>1 and w not in STOP]
def project(r):
    text=r['candidates'] or '';segments=START.split(text); assert not text.strip() or len(segments)>1
    els=[]
    for uid,raw in zip(segments[1::2],segments[2::2]):
        m=TAG.search(raw);tag=m.group(1).lower() if m else 'unknown'
        edit=tag in ('input','select','textarea') or bool(re.search(r'contenteditable=[\x22\x27]?true',raw,re.I))
        doc=words(re.sub(r'\[\[(?:xpath|bbox)\]\][^\[]+|[0-9a-f]{8}-[0-9a-f-]+','',raw,flags=re.I))
        els.append((uid,tag,edit,Counter(doc)))
    uids=[e[0] for e in els];assert len(uids)==len(set(uids))
    speech=SPEECH.findall(r['action_history'] or '')
    q=words(speech[-1] if speech else '')
    # A lexical screen-only sanity check. Author ranking is the stable tie-break.
    score=[sum((1+math.log((len(els)+1)/(1+sum(w in x[3] for x in els))))*int(w in e[3]) for w in set(q)) for e in els]
    j=max(range(len(els)),key=lambda i:score[i]) if els else None
    a=r['action'];target=UID.search(a)
    return {'demo':r['demo'],'turn':int(r['turn']),'c':[[u,t,b] for u,t,b,_ in els],
        'lex':None if j is None else uids[j],'k':a.partition('(')[0],'y':target.group(1) if target else None}
def main():
    sources=json.loads((ROOT/'sources.json').read_bytes()); assert [x['split'] for x in sources]==SPLITS
    dest=ROOT/'rows';dest.mkdir(exist_ok=True);locks={}
    for s in sources:
        p=ROOT/'raw'/(s['split']+'.json.gz');assert hashlib.sha256(p.read_bytes()).hexdigest()==s['sha256']
        out=dest/p.name
        with gzip.open(p,'rt',encoding='utf8') as io,out.open('wb') as fp,gzip.GzipFile(fileobj=fp,mode='wb',mtime=0,filename='') as sink:
            for line in io:sink.write((json.dumps(project(json.loads(line)),separators=(',',':'))+'\n').encode())
        locks[out.relative_to(ROOT).as_posix()]=hashlib.sha256(out.read_bytes()).hexdigest()
    (ROOT/'projection_hashes.json').write_text(json.dumps(locks,indent=1))
if __name__=='__main__':main()
