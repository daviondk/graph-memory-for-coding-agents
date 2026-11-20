"""Extract issue-conditioned graph evidence strictly from candidate blobs at the old commit."""
import ast,collections,functools,gzip,hashlib,io,json,math,random,re,sys,time,tokenize,warnings
from pathlib import Path,PurePosixPath
from concurrent.futures import ProcessPoolExecutor
warnings.simplefilter("ignore",SyntaxWarning)
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from rank import STOP,tokens,digest
RX=re.compile(r"\b[A-Za-z_][A-Za-z_0-9]{2,79}\b")
IGNORE={"self","cls","true","false","none","def","elif","else","raise","pass","except","import","print","class","args","kwargs","data","str","get","set","object","try","list","int","bool","type","dict"}
BA=["native_rr","native_first","path_term","path_literal","basename_literal","word_bm25","ident_bm25","code_ident_bm25","file_token_coverage","code_ident_coverage","source_available"]
LOCAL=["local_declaration","local_use","local_declaration_code","local_use_code"]
LINK=["owner_shared_use","user_shared_owner","owner_explicit_import","user_explicit_import","owner_unique_cross","user_unique_cross"]
def meaningful(x):return x.lower() not in STOP|IGNORE and len(x)>2
def shaped(s):return "_" in s.strip("_") or (s.lower()!=s and s.upper()!=s and any(c.isupper() for c in s[1:])) or (len(s)>=3 and s.isupper())
def text_bytes(b):
    try: enc,_=tokenize.detect_encoding(io.BytesIO(b).readline);return b.decode(enc)
    except (UnicodeError,SyntaxError):return b.decode("utf8","replace")
@functools.lru_cache(maxsize=90)
def facts(oid):
    p=HERE/"sources"/(oid+".gz")
    if not p.exists():return None
    b=gzip.decompress(p.read_bytes())
    assert hashlib.sha1(b"blob "+str(len(b)).encode()+b"\x00"+b).hexdigest()==oid
    txt=text_bytes(b)
    words=collections.Counter(tokens(txt));all_ids=collections.Counter(x.group() for x in RX.finditer(txt) if meaningful(x.group()))
    decl=set();uses=set();imports=set()
    try:tree=ast.parse(b)
    except (SyntaxError,UnicodeError,ValueError):return words,all_ids,decl,uses,imports,False
    for node in ast.walk(tree):
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):decl.add(node.name)
        if isinstance(node,(ast.Module,ast.ClassDef)):
            for it in node.body:
                if isinstance(it,ast.Assign):
                    decl.update(v.id for v in it.targets if isinstance(v,ast.Name))
                elif isinstance(it,ast.AnnAssign) and isinstance(it.target,ast.Name):decl.add(it.target.id)
        if isinstance(node,ast.Name) and isinstance(node.ctx,ast.Load):uses.add(node.id)
        if isinstance(node,ast.Attribute) and isinstance(node.ctx,ast.Load):uses.add(node.attr)
        if isinstance(node,ast.ImportFrom):
            for al in node.names:imports.add(al.name.rsplit(".",1)[-1]);uses.add(al.name.rsplit(".",1)[-1])
    return words,all_ids,decl,uses,imports,True
def bm25(doc,q,df,n,avg):
    length=sum(doc.values());score=0.
    for w,weight in q.items():
        t=doc.get(w)
        if t:
            idf=math.log(1+(n-df[w]+.5)/(df[w]+.5))
            score+=weight*idf*t*2.2/(t+1.2*(.25+.75*length/max(1,avg)))
    return score
def summarize(r):
    paths=r["paths"];n=len(paths);q=r["question"][:40000]
    qi=collections.Counter(x.group() for x in RX.finditer(q) if meaningful(x.group()))
    qw={t:min(2,c) for t,c in collections.Counter(tokens(q)).items()}
    # Cues resembling actual identifiers are grounded by roles; all tokens still enter the flat controls.
    code={x.group() for x in re.finditer(r"\b[A-Za-z_]\w*(?=\s*\()",q)}
    code.update(x for x in qi if shaped(x));code.update(t for chunk in re.findall(r"\x60([^\x60 \n]{1,100})\x60",q) for t in RX.findall(chunk))
    code.update(t for g in re.findall(r"\b(?:[A-Za-z_]\w*\.)+[A-Za-z_]\w*\b",q) for t in g.split("."))
    qiw={t:min(2,c) for t,c in qi.items()};qcw={k:v for k,v in qiw.items() if k in code}
    data=[];success=0;astok=0
    for p in paths:
        x=facts(r["blobs"].get(p,"absent"))
        if x is None:x=(collections.Counter(),collections.Counter(),set(),set(),set(),False)
        else:success+=1
        astok+=int(x[-1]);data.append(x)
    docfreq=[collections.Counter(k for d in data for k in d[i]) for i in (0,1)]
    avgs=[sum(sum(d[i].values()) for d in data)/max(1,n) for i in (0,1)]
    def presence_weight(t):
        return min(2,qi[t])*(2 if t in code else 1)*math.log(1+(n+.5)/(docfreq[1].get(t,0)+.5))
    # Shuffle only the typed edges (decl/use/import). Preserve token identities, per-file counts
    # and overlap between roles within a file by applying one bijection to its full role vocabulary.
    def role_values(shuffle):
        dlist=[];ulist=[];ilist=[]
        for p,(_,ids,dd,uu,ii,_) in zip(paths,data):
            if shuffle:
                vocabulary=sorted(dd|uu|ii)
                perm=sorted(vocabulary,key=lambda t:hashlib.sha256((r["id"]+"|"+p+"|"+t).encode()).digest())
                repl=dict(zip(vocabulary,perm))
                dd={repl[t] for t in dd};uu={repl[t] for t in uu};ii={repl[t] for t in ii}
            dlist.append(dd&qi.keys());ulist.append(uu&qi.keys());ilist.append(ii&qi.keys())
        owner=collections.Counter(t for ids in dlist for t in ids)
        res=[]
        for i,(dd,uu) in enumerate(zip(dlist,ulist)):
            item=dict.fromkeys(LOCAL+LINK,0.)
            for tag,ids in (("local_declaration",dd),("local_use",uu)):
                item[tag]=sum(presence_weight(t) for t in sorted(ids))
                item[tag+"_code"]=sum(presence_weight(t) for t in sorted(ids&code))
            for t in sorted(dd):
                o=sum(t in ul for j,ul in enumerate(ulist) if i!=j)
                k=sum(t in il for j,il in enumerate(ilist) if i!=j)
                if o:
                    item["owner_shared_use"]+=presence_weight(t)*math.log2(1+o)/owner[t]
                    item["owner_unique_cross"]+=presence_weight(t)*(owner[t]==1 and t in code)
                item["owner_explicit_import"]+=presence_weight(t)*int(bool(k))/owner[t]
            for t in sorted(uu):
                os=owner[t]-int(t in dd)
                if os>0:
                    item["user_shared_owner"]+=presence_weight(t)/os
                    item["user_unique_cross"]+=presence_weight(t)*(owner[t]==1 and t in code)
                    item["user_explicit_import"]+=presence_weight(t)*(t in ilist[i])/os
            res.append(item)
        return res
    real=role_values(False);shuffled=role_values(True)
    features=[]
    lower=q.lower().replace("\\","/")
    for rank,(path,(wd,ids,_,_,_,_)) in enumerate(zip(paths,data),1):
        basename=PurePosixPath(path).name.lower();pt=set(tokens(path))
        v={"native_rr":1/rank,"native_first":int(rank==1),"path_term":sum(qw.get(t,0) for t in pt)/math.sqrt(1+len(pt)),
           "path_literal":int(path.lower() in lower),"basename_literal":int(basename in lower and basename!="__init__.py"),
           "word_bm25":bm25(wd,qw,docfreq[0],n,avgs[0]),"ident_bm25":bm25(ids,qiw,docfreq[1],n,avgs[1]),
           "code_ident_bm25":bm25(ids,qcw,docfreq[1],n,avgs[1]),"file_token_coverage":sum(qw.get(x,0) for x in wd.keys()&qw.keys()),
           "code_ident_coverage":sum(qcw.get(x,0) for x in ids.keys()&qcw.keys()),"source_available":int(bool(wd))}
        v.update(real[rank-1]);v.update({"perm_"+k:z for k,z in shuffled[rank-1].items()});features.append(v)
    # Stable common scaling per slate without labels; rank positions and binary features stay absolute.
    for k in (BA+LOCAL+LINK+["perm_"+x for x in LOCAL+LINK]):
        denom=max([1.0]+[f[k] for f in features])
        for f in features:f[k]/=denom
    return {"id":r["id"],"source":r["source"],"repo":r["repo"],"base":r["base"],"date":r["date"],"paths":paths,
            "excluded":r["excluded"],"n_blobs":success,"n_ast":astok,"features":features}
def main():
    rows=json.loads(gzip.decompress((HERE/"inputs.json.gz").read_bytes()))
    with ProcessPoolExecutor(max_workers=4) as ex:records=list(ex.map(summarize,rows,chunksize=8))
    p=HERE/"features.jsonl.gz"
    p.write_bytes(gzip.compress(("\n".join(json.dumps(r,sort_keys=True,separators=(",",":")) for r in records)+"\n").encode(),mtime=0))
    receipt={n:digest(HERE/n) for n in ["PROTOCOL.md","inputs.json.gz","source_receipt.json","features.py",p.name]}
    (HERE/"feature_lock.json").write_text(json.dumps(receipt,indent=2),encoding="utf8")
    print("rosters",collections.Counter(r["source"] for r in records),"blob",sum(r["n_blobs"] for r in records),"AST",sum(r["n_ast"] for r in records),flush=True)
if __name__=="__main__":main()

