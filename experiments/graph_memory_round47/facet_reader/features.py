"""Reconstruct exactly the Qwen-visible bytes and extract public structured lexical features."""
from pathlib import Path
from collections import Counter
import struct,re,json,gzip,hashlib,math,os
import numpy as np
D=Path(__file__).resolve().parent;W=D.parents[1]
R45=W/'graph_memory_round45/qwen_panel214';R46=W/'graph_memory_round46/set_reader'
R34=W/'graph_memory_round34/external_transfer';PUB=W/'memory_session5/serbench/upstream/data/cal500'
CACHE=Path('D:/CodexResearch/x20-r39-embedding-runtime')
GG=Path('D:/CodexResearch/x20-r46-small-reranker/Qwen3-Reranker-0.6B-Q4_K_M.gguf')
TOK=CACHE/'runs-r40-lexical-native-input/matched-tokens.json.gz'
PROTOCOL='40115ede05aebe6053b0bab102b56b75f52c70a3b567efe3e409df1bfe14cc8a'
ROLES=('behavior_constraint','bug_location','api_constraint','other')
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):
    v=p.read_bytes();return json.loads(gzip.decompress(v) if p.suffix=='.gz' else v)
def write(name,value):
    b=(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
    (D/name).write_bytes(gzip.compress(b,mtime=0,compresslevel=4) if name.endswith('.gz') else b)
def signed(p,k):
    assert sha(p/k)==read(p/'manifest.json')['files'][k]
    return read(p/k)
def vocab(path):
    fixed={0:1,1:1,2:2,3:2,4:4,5:4,6:4,7:1,10:8,11:8,12:8}
    with path.open('rb') as f:
        def st():return f.read(struct.unpack('<Q',f.read(8))[0])
        def obj(t,keep=False):
            if t==8:
                b=st();return b.decode('utf8') if keep else None
            if t==9:
                k,n=struct.unpack('<IQ',f.read(12))
                if not keep and k in fixed:f.seek(n*fixed[k],1);return
                if keep:return [obj(k,True) for i in range(n)]
                for i in range(n):obj(k)
            else:f.seek(fixed[t],1)
        assert f.read(4)==b'GGUF';v,_,count=struct.unpack('<IQQ',f.read(20));assert v==3
        for i in range(count):
            k=st();t=struct.unpack('<I',f.read(4))[0]
            if k==b'tokenizer.ggml.tokens':return obj(t,True)
            obj(t)
    raise ValueError('GGUF vocabulary missing')
def decoder():
    # GPT-2 byte alphabet used by Qwen. Special strings in ordinary text are split into ordinary BPE tokens upstream.
    bs=list(range(33,127))+list(range(161,173))+list(range(174,256));cs=bs[:]
    for b in range(256):
        if b not in bs:bs.append(b);cs.append(256+len(cs)-(94+12+82))
    lookup=dict(zip(map(chr,cs),bs))
    return [bytes(lookup[ch] for ch in w) if all(ch in lookup for ch in w) else w.encode() for w in vocab(GG)]
def ranks(scores):
    return np.argsort(np.argsort(-np.asarray(scores),kind='stable'),kind='stable')+1
def role(k):return ROLES.index(k) if k in ROLES else 3
def labels(qids):
    out={}
    with gzip.open(PUB/'labels.jsonl.gz','rt',encoding='utf8') as f:
        for line in f:
            z=json.loads(line)
            if z['state_id'] in qids:out[z['state_id']]=z
    assert set(qids)==set(out)
    return out
def targets(ids,label):
    target=np.zeros((len(ids),4),int);idx={k:i for i,k in enumerate(ids)};demand=np.zeros(4,int)
    for group in label['required_evidence_groups']:
        aspect=role(group['role']);demand[aspect]=1
        for c in group['acceptable_evidence_ids']:
            if c in idx:target[idx[c],aspect]=1
    return target,demand
ID=re.compile(r'[A-Za-z_][A-Za-z_0-9]{1,}')
IGNORE=set('the this that for from when and with return true false none self into or at an of to is are be as in it if function should implementation some code issue file current query can bying all from import test class def'.split())
def words(s):
    raw=ID.findall(s);v=[]
    for x in raw:
        a=x.lower()
        if len(a)>1 and a not in IGNORE:v.append(a)
        b=re.sub(r'([a-z0-9])([A-Z])',r'\1_\2',x).lower().split('_')
        if len(b)>1:v.extend(w for w in b if len(w)>1 and w not in IGNORE)
    return v
CUES=('behavio|expect|should|output|incorrect','locat|where|root cause|responsib|caus','api|signature|argument|paramet|contract','test|assert|verif|fixture','call|uses?|interact|depend','history|prior|previous|commit','class|method|function|implement','error|fail|exception|raises','config|option|setting','docum|example|readme','reproduc|reported|traceback','file|module|path')
DECL=re.compile(r'\b(?:def|class|function|func|fn|struct|enum|interface|trait|type)\s+([A-Za-z_]\w*)');CALL=re.compile(r'\b([A-Za-z_]\w*)\s*\(')
def qviews(t):
    t=t.split('Query: ',1)[-1];pieces=t.split('\n',2)
    return [t]+(pieces+['',''])[:3]
def describe(s):
    p,_,t=s.partition('\n');ls=t.lower();tokens=Counter(words(t));fields=(tokens,Counter(words(p)),Counter(words(' '.join(DECL.findall(t)))),Counter(words(' '.join(CALL.findall(t)))))
    tests=bool(re.search(r'(^|[/.\\_-])(tests?|specs?)([/.\\_-]|$)',p.lower()))
    f=[math.log1p(len(t)),math.log1p(len(tokens)),math.log1p(len(t.splitlines())),float(tests),math.log1p(p.count('/')),
       float(bool(re.search(r'(^|/)(doc|docs|examples?)(/|$)|\.md$',p.lower()))),float(bool(re.search(r'\.(yaml|json|toml|ini|yml)$',p.lower())))]
    f += [math.log1p(len(re.findall(rx,ls))) for rx in (r'\bdef\s',r'\bclass\s',r'\bassert',r'\braise',r'\breturn',r'\bimport',r'\bif',r'\btest_',r'\bself\.',r'\bexcept',r'=>|->',r'^\s*#|/\*',r'\bclass\s|interface\s|struct\s')]
    return p,fields,f
def features(query,docs):
    parts=qviews(query);qs=[Counter(words(s)) for s in parts];qc=[float(bool(re.search(rx,s.lower()))) for s in parts for rx in CUES]
    qstats=qc+[math.log1p(len(x)) for x in qs]+[math.log1p(len(s.splitlines())) for s in parts]
    n=len(docs);df=Counter();lens=[]
    for _,d,_ in docs:
        df.update(set(d[0])|set(d[1]));lens.append(sum(d[0].values())+sum(d[1].values()))
    idf={k:math.log(1+(n-v+.5)/(v+.5)) for k,v in df.items()};avg=max(1,sum(lens)/n)
    allrows=[];allbm=[]
    for (p,fields,dfx),l in zip(docs,lens):
        row=list(dfx);bm=0.
        for j,q in enumerate(qs):
            for f in fields:
                joint=f.keys()&q.keys()
                overlap=sum(idf.get(x,0.) for x in sorted(joint))
                row.extend((math.log1p(overlap),len(joint)/(1+len(q)),len(joint)/(1+len(f))))
            if j==0:
                tf=fields[0]+fields[1]
                bm=sum(idf[x]*(2.2*tf[x])/(tf[x]+1.2*(.25+.75*l/avg)) for x in sorted(q.keys()&tf.keys()))
        low=p.lower();row.extend((float(low in parts[0].lower() and bool(low)),float(low.rsplit('/',1)[-1] in parts[0].lower() and bool(low))))
        row.extend(qc[:12]);row.extend([qc[i]*dfx[3] for i in range(12)]);row.extend([qc[i]*math.log1p(len(fields[2])) for i in range(12)])
        allrows.append(row);allbm.append(bm)
    br=ranks(allbm)
    for i,(row,bm) in enumerate(zip(allrows,allbm)):row.extend((math.log1p(bm),1/math.sqrt(br[i]),bm/(1+max(allbm))))
    return np.asarray(allrows),np.asarray(qstats),br
def main():
    assert sha(D/'PROTOCOL_RU.md')==PROTOCOL and sha(TOK)==signed(R45,'matched-token-seal.json')['forecasts_input']
    bundle=read(TOK);states=bundle['states'];rows=read(R34/'features.json.gz');tokens=bundle['tokens'];tab=decoder()
    assert sha(GG)=='5290f5b9a2636be40baf807feafcfb222e0c4670a083fb3447d87993566190a9'
    def decode(k):
        n,vs=tokens[k];s=b''.join(tab[i] for i in vs[:-1]).decode('utf8',errors='replace')
        if n<=512:assert hashlib.sha256(s.encode()).hexdigest()==k
        return s
    out={};cache={}
    for q,v in states.items():
        for k in v['doc']:
            if k not in cache:cache[k]=describe(decode(k))
        x,u,br=features(decode(v['three']),[cache[k] for k in v['doc']])
        out[q]={'x':x.astype('float32').round(6).tolist(),'u':u.tolist(),'lex':br.tolist(),'ids':v['ids'],'seen':v['seen'],'repo':rows[q]['repo'],'split':rows[q]['split']}
    # Large numerical features are recoverable runtime, kept outside portable evidence.
    fp=CACHE/'r47-role-features.json.gz';b=(json.dumps(out,separators=(',',':'))+'\n').encode()
    fp.write_bytes(gzip.compress(b,compresslevel=3,mtime=0));allkeys={st['three'] for st in states.values()}|set(cache)
    write('feature-seal.json',dict(n=len(out),rows=sum(len(v['ids']) for v in out.values()),vectors=len(allkeys),verified_text_hashes=sum(tokens[k][0]<=512 for k in allkeys),
          source=sha(TOK),split=sha(R34/'features.json.gz'),numeric=sha(fp),program=sha(Path(__file__)),doc_dims=len(next(iter(out.values()))['x'][0]),q_dims=len(next(iter(out.values()))['u'])))
    print('Sealed',len(out),'states and',len(cache),'unique candidate excerpts.')
if __name__=='__main__':main()

