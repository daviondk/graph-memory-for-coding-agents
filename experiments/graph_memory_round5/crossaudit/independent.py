"""Independent Java scoring from public author functions and a second scalar implementation."""
import ast,collections,difflib,functools,gzip,hashlib,itertools,json,math,re,sys,tarfile
from pathlib import Path
import numpy as np
D=Path(__file__).resolve().parent; INPUT=D.parent/'crosscode';sys.path.insert(0,str(D/'vendor'))
from fuzzywuzzy import fuzz
from nltk.tokenize import RegexpTokenizer
def read(p):
    raw=p.read_bytes()
    return json.loads(gzip.decompress(raw) if p.suffix=='.gz' else raw)
def hash_b(value):return hashlib.sha256(value).hexdigest()
def sha(path):return hash_b(path.read_bytes())
def save(name,data): (D/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
KEYS=['em','es','id_em','id_f1']
def definitions(name,funcs,constants,env):
    root=ast.parse((D/name).read_text(encoding='utf8'))
    chosen=[nd for nd in root.body if (isinstance(nd,ast.FunctionDef) and nd.name in funcs)
        or (isinstance(nd,ast.Assign) and any(isinstance(k,ast.Name) and k.id in constants for k in nd.targets))]
    exec(compile(ast.Module(body=chosen,type_ignores=[]),name,'exec'),env)
def official():
    assert fuzz.SequenceMatcher is difflib.SequenceMatcher
    pin=read(D/'upstream.json');assert all(sha(D/f)==v['sha256'] for f,v in pin.items())
    words=set((D/'java.txt').read_text().split())
    env={'re':re,'fuzz':fuzz,'RegexpTokenizer':RegexpTokenizer,'get_language_keywords':lambda lang:words,
         'parser':None}
    definitions('eval_utils.py',{'cal_edit_sim','extract_identifiers','is_identifier','remove_comments','get_bracket_lang_statement','postprocess_code_lines'},{'code_tokenizer','IDENTIFIER_REGEX','string_pattern'},env)
    definitions('eval_metric.py',{'compute_id_match','process_examples'},set(),env)
    return env
AUTHOR=official()
def chatwrap(text):return '\n'.join(text.split('\n')[1:]).strip(chr(96)) if text.startswith(chr(96)*3) else text
def evaluate_a(out,ref,uid):
    pred,exact=AUTHOR['process_examples']('java',({'task_id':uid,'pred':chatwrap(out)},{'prompt':'','groundtruth':ref}))
    tp,fp,fn=AUTHOR['compute_id_match'](pred['pred_ids'],pred['target_ids'])
    n=2*tp+fp+fn
    return [exact,AUTHOR['cal_edit_sim']([pred['target']],[pred['pred']])/100,
            int(pred['pred_ids']==pred['target_ids']),2*tp/n if n else 0.]
WORDS=set((D/'java.txt').read_text().split())
def evaluate_b(raw,ref):
    text=chatwrap(raw)
    delim=re.search('[;{}]',text)
    if delim and delim.start()>0:text=text[:delim.end()]
    def clean(x):return re.sub(r'//[^\n]*','',re.sub(r'#[^\n]*','',x))
    a,b=map(clean,(text,ref))
    trim=lambda x:[s.strip() for s in x.split('\n') if s.strip()]
    def ids(x):
        x=re.sub(r'''(?:"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')''','',x)
        return [s for s in re.findall(r'\w+',x) if re.match('[A-Za-z_]',s) and s not in WORDS]
    p,q=ids(a),ids(b);s,t=set(p),set(q)
    es=round(100*difflib.SequenceMatcher(None,a.strip(),b.strip()).ratio())/100
    return [int(trim(a)==trim(b)),es,int(p==q),2*len(s&t)/(len(s)+len(t)) if s or t else 0.]
def test():
    for a,b in [('',''),('; next();','; next();'),('   ; next();',';'),('F(x,x);','F(x);'),('x="http://foo";','x="http://foo";'),('a #xx\nb;','a\nb;'),('String αName = "X";','String αName = "x";'),('F(a, b, a);','F(b, a);'),(chr(96)*3+'java\nf();\n'+chr(96)*3,'f();'),("x='foo\\'bar';","x='foo';")]:
        assert evaluate_a(a,b,'t')==evaluate_b(a,b),(a,b,evaluate_a(a,b,'t'),evaluate_b(a,b))
def locked(p):
    for name,hash_ in read(INPUT/f'{p}_input_lock.json').items():assert sha(INPUT/name)==hash_
    datal=read(INPUT/f'{p}_data_lock.json')
    for name,hash_ in datal['sha'].items(): assert sha(INPUT/name)==hash_
    ix=read(INPUT/f'{p}_assignment.json')
    manifest=read(INPUT/f'{p}_decisions.json'); required={h+'.json.gz' for rec in ix.values() for h in rec.values()}
    assert required==set(manifest)=={path.name for path in (INPUT/(p+'_calls')).glob('*.json.gz')}
    calls={}; fenc=0
    for name,h in manifest.items():
        path=INPUT/(p+'_calls')/name;assert sha(path)==h
        rec=read(path);req=rec['request']
        canonical=json.dumps(req,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()
        assert hash_b(canonical)+'.json.gz'==name
        raw=rec['reply']['choices'][0]['message']['content']
        assert isinstance(raw,str)
        calls[name.split('.')[0]]=raw
        fenc+=raw.startswith(chr(96)*3)
    return ix,calls,fenc,sha(INPUT/f'{p}_decisions.json')
def compare(scored,roster,methods,denom):
    gid=sorted({r['repo'] for r in roster}); m=len(gid); bins=np.zeros((m,5))
    valid={r['id'] for r in roster};assert len(valid)==denom
    for row in roster:bins[gid.index(row['repo']),-1]+=1
    a,b=methods
    hits=loss=0
    for r in scored:
        if r['id'] not in valid:continue
        dif=np.asarray(r[a])-r[b];bins[gid.index(r['repo']),:4]+=dif;hits+=dif[0]>0;loss+=dif[0]<0
    sums=bins.sum(axis=0); vals=bins[:,0]; nz=vals[vals!=0].astype(int)
    if len(nz)<=18:
        p=sum(abs(np.dot(sign,nz))>=abs(nz.sum()) for sign in itertools.product((-1,1),repeat=len(nz)))/2**len(nz)
    else:
        rng=np.random.default_rng(1151); exc=0
        for _ in range(100):exc+=(abs(rng.choice((-1,1),(1000,len(nz)))@nz)>=abs(nz.sum())).sum()
        p=(exc+1)/100001
    rng=np.random.default_rng(150515);boot=[]
    for _ in range(100):
        total=bins[rng.integers(m,size=(100,m))].sum(axis=1);boot.extend(total[:,:4]/total[:,4:])
    cis=np.quantile(boot,[.025,.975],axis=0).T*100
    return dict(n=denom,projects=m,wins=int(hits),losses=int(loss),metric_delta_pp=dict(zip(KEYS,(sums[:4]/denom*100).tolist())),cluster_boot95_pp=dict(zip(KEYS,cis.tolist())),signflip_task_project=float(p))
def score():
    test()
    # Both hashes must exist and cover the complete call sets before the archive is opened.
    seals={p:locked(p) for p in ('D','E')}
    cl=read(INPUT/'D_data_lock.json');archive=INPUT/'crosscodeeval_data.tar.xz'
    assert sha(archive)==cl['data_hash']
    union=set().union(*(x[0] for x in seals.values()));gt={}
    with tarfile.open(archive) as tf:
        for line in tf.extractfile(cl['member']):
            raw=json.loads(line);uid=raw['metadata']['task_id']
            if uid in union:gt[uid]=raw['groundtruth']
    assert set(gt)==union
    out={}
    for p,(ix,calls,fenc,h) in seals.items():
        packets=read(INPUT/f'{p}_packets.json.gz');packets={r['id']:r for r in packets};scored=[]
        assert set(ix)==set(packets)
        for uid,arms in ix.items():
            rec={'id':uid,'repo':packets[uid]['repo']}
            for a,k in arms.items():
                ref=gt[uid];pred=calls[k];v=evaluate_a(pred,ref,uid)
                alt=evaluate_b(pred,ref);assert np.allclose(v,alt,rtol=0,atol=1.e-12),(uid,a,v,alt)
                rec[a]=v
            scored.append(rec)
        arms=sorted(next(iter(ix.values())))
        submean={m:dict(zip(KEYS,(100*np.mean([r[m] for r in scored],axis=0)).tolist())) for m in arms}
        pop=read(INPUT/'E_population.json.gz') if p=='E' else list(packets.values())
        if p=='E':
            assert len({r['id'] for r in pop})==len(pop)
            assert {r['id'] for r in pop if r['eligible'] and r['changed']}==set(ix)
            for r in pop:
                if r['eligible']:assert r['changed']==(r['hashes'][0]!=r['hashes'][1])
            for uid,r in packets.items():
                a,b=r['snippets']['order'][0],r['snippets']['bridge'][0]
                meta=next(z for z in pop if z['id']==uid)
                assert [hash_b(x.encode()) for x in (a,b)]==meta['hashes'] and a!=b
            pop=[r for r in pop if r['eligible']]
        out[p]={'metrics_order':KEYS,'decision_hash':h,'unique_requests':len(calls),'fenced_outputs':fenc,'scored_task_absolute_metrics_percent':submean,
                'absolute_metrics_denominator':len(scored),'all_bridge_minus_order':compare(scored,pop,('bridge','order'),len(pop))}
        if p=='E':
            unknown=[r for r in pop if not r['known']]
            out[p]['new_projects_bridge_minus_order']=compare(scored,unknown,('bridge','order'),len(unknown))
            active=[r for r in pop if r['changed']]
            out[p]['changed_only_bridge_minus_order']=compare(scored,active,('bridge','order'),len(active))
        with gzip.open(D/f'{p}_independent_rows.jsonl.gz','wt',encoding='utf8') as f:
            for row in scored:f.write(json.dumps(row,separators=(',',':'))+'\n')
    save('independent_results.json',out)
    print(json.dumps(out,indent=1))
if __name__=='__main__':
    if len(sys.argv)==1 or sys.argv[1]=='score':score()
    else:test();print('All paired scalar unit fixtures passed.')

