import ast,base64,difflib,io,token,tokenize,statistics
from collections import Counter,defaultdict
from qutil import Q,R9,load,put,sha
from exact import direct
def signature(text):
    skip=set()
    for a in ast.walk(ast.parse(text)):
        if isinstance(a,ast.Expr) and isinstance(a.value,ast.Constant) and isinstance(a.value.value,str):
            skip.update(range(a.lineno,a.end_lineno+1))
    rows=defaultdict(list);depth=0
    for t in tokenize.generate_tokens(io.StringIO(text).readline):
        if t.type==tokenize.INDENT:depth+=1;continue
        if t.type==tokenize.DEDENT:depth-=1;continue
        if t.type in {tokenize.NEWLINE,tokenize.NL,tokenize.COMMENT,tokenize.ENDMARKER,tokenize.ENCODING} or t.start[0] in skip:continue
        rows[t.start[0]].append((depth,t.type,t.string))
    return [(n,tuple(v)) for n,v in sorted(rows.items())]
def delta(a,b):
    sig,other=signature(a),signature(b);changed=set()
    for tag,i,j,k,h in difflib.SequenceMatcher(None,[x[1] for x in sig],[x[1] for x in other],autojunk=False).get_opcodes():
        if tag=='equal':continue
        ids=range(i,j) if i!=j else [z for z in (i-1,i) if 0<=z<len(sig)]
        changed.update(sig[z][0] for z in ids)
    return changed
def main():
    totals=defaultdict(Counter);directions=[];read=[]
    for p in sorted((Q/'states').glob('*.gz')):
        x=load(p);t=x['task'];d=x['direction'];opposite='base' if d=='gold' else 'gold'
        src=R9/'agentvalue'/'tasks'/t;loadcode=lambda s:(src/s/'checkout'/'python_programs'/(t+'.py')).read_text(encoding='utf8')
        q=delta(loadcode(d),loadcode(opposite));sets=load(Q/'old'/p.name)['sets'];labs=load(Q/'future'/p.name)['labels'];n=len(sets)
        ref=sum(1<<i for i,a in enumerate(sets) if set(a)&q);flip=sum(1<<i for i,(v,w) in enumerate(labs) if v!=w)
        union=set().union(*(set(v) for v in sets))
        directions.append(dict(task=t,old=d,changed=sorted(q),old_overlap=len(union&q),exact=ref.bit_count(),flips=flip.bit_count(),exact_missed=(flip&~ref).bit_count()))
        for b,s,a,enc,_ in x['states']:
            pred=direct(base64.b64decode(enc),list(map(str,q)));assert pred&ref==ref
            vals=dict(extra=(pred^ref).bit_count(),stale=(flip&~pred).bit_count(),n=n,flips=flip.bit_count(),rerun=pred.bit_count(),exact=ref.bit_count())
            totals[b,a,s].update(vals);read.append([t,d,b,s,a,ref,pred,vals])
    out={}
    for b in [16,64,256]:
        out[b]={}
        for a in sorted({a for bb,a,s in totals}):
            out[b][a]={m:statistics.mean(totals[b,a,s][m] for s in range(32)) for m in totals[b,a,0]}
    put(Q/'semantic_results.json',dict(summary=out,directions=directions));put(Q/'semantic_rows.json.gz',read)
if __name__=='__main__':main()