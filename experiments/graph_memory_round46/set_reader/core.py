from pathlib import Path
import gzip,hashlib,json,time
from collections import Counter
import numpy as np
from scipy.sparse import csr_matrix
D=Path(__file__).resolve().parent;W=D.parents[1];P=W/'graph_memory_round45/qwen_panel214'
TOK=Path('D:/CodexResearch/x20-r39-embedding-runtime/runs-r40-lexical-native-input/matched-tokens.json.gz')
def read(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix=='.gz' else b)
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write(n,data):
    b=(json.dumps(data,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)+'\n').encode()
    (D/n).write_bytes(gzip.compress(b,mtime=0,compresslevel=4) if n.endswith('.gz') else b)
def signed(p,n):
    assert sha(p/n)==read(p/'manifest.json')['files'][n]
    return read(p/n)
def cosine(token_lists):
    docs=[Counter(x[:-1]) for x in token_lists];vocab={k:i for i,k in enumerate(sorted(set().union(*(d.keys() for d in docs))))}
    df=Counter()
    for d in docs:df.update(d.keys())
    vals=[];cols=[];ind=[0]
    for doc in docs:
        w=np.array([(1+np.log(c))*(1+np.log((len(docs)+1)/(df[k]+1))) for k,c in doc.items()])
        if len(w):w/=np.linalg.norm(w)
        vals.extend(w.tolist());cols.extend(vocab[k] for k in doc);ind.append(len(vals))
    x=csr_matrix((vals,cols,ind),shape=(len(docs),len(vocab)))
    g=(x@x.T).toarray()
    # A document with zero content gets an independent unit direction.
    np.fill_diagonal(g,1)
    return g
def rank(K,order,beta,mode='dpp',seen=None,scope=None):
    n=len(order);scope=list(range(n)) if scope is None else scope;unary=np.empty(n);unary[order]=-np.log(np.arange(n)+1)
    observed=[] if seen is None else [i for i in scope if seen[i]]
    available=[i for i in scope if i not in set(observed)]
    gram=K*beta+(1-beta)*np.eye(n);diag=np.diag(gram).copy();basis=[];maximal=np.zeros(n);selected=[]
    def update(i):
        prev=np.asarray(basis)
        v=(gram[i]-(prev[:,i]@prev if len(basis) else 0))/np.sqrt(max(diag[i],1e-12))
        basis.append(v);diag[:]=np.maximum(diag-v*v,1e-12);maximal[:]=np.maximum(maximal,(beta*K[i])**2)
    if mode in ('history','historic_static'):
        for i in observed:update(i)
    historic=diag.copy();rem=set(available)
    while rem:
        if mode=='mmr':bonus=np.log(np.maximum(1-maximal,1e-12))
        elif mode=='historic_static':bonus=np.log(historic)
        else:bonus=np.log(diag)
        i=min(rem,key=lambda j:(-float(unary[j]+bonus[j]),j));rem.remove(i);selected.append(i)
        if mode!='historic_static':update(i)
    selected.extend(i for i in order if i in set(observed));return selected

