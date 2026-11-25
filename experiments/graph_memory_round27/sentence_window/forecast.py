from data import *
from operators import Reader,makeops,bill,equal
from tokenizers import Tokenizer
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
import sys
os.environ['RAYON_NUM_THREADS']='1';os.environ['TOKENIZERS_PARALLELISM']='false'
ARMS=('both','window','boundary_window')
def setup():
    freeze();nrec=read(D/'native-receipt.json');assert sha(D/'sentence-index.json.gz')==nrec['index']
    rec={'plan':sha(D/'plan.json'),'native':sha(D/'native-receipt.json'),'ops':sha(D/'operators.py'),'forecast':sha(Path(__file__)),'scoring':sha(D/'outcomes.py'),'prior_rule':sha(OLD/'direction.py'),'query_ranker':sha(WORK/'graph_memory_round23/marginal_open/novelty.py')}
    f=D/'operator-lock.json'
    if f.exists():assert read(f)==rec
    else:assert not list(D.glob('pred-*.json.gz'));save(f,rec)
def worker(shard):
    name,h=read(PRIOR/'choices-lock.json')['files'][shard];assert sha(PRIOR/name)==h
    before=read(PRIOR/name)
    name,h=read(PRIOR/'read-lock.json')['files'][shard];assert sha(PRIOR/name)==h
    native=read(PRIOR/name)
    tok=Tokenizer.from_file(str(TOK));index=read(D/'sentence-index.json.gz')
    groups=defaultdict(list)
    for q,record in before.items():groups[record['t']].append(q)
    data={}
    for article in read(RAW)['data']:
        t=article['title']
        if t not in groups:continue
        src=body(article);query=querytexts(article);engine=Reader(src,index[t]['s'],tok)
        for q in sorted(groups[t]):
            old=before[q];job=engine.block(query[q],old['base'],old['cut'])
            if job is None:fn=lambda method,cap:([],0);info={}
            else:fn,info=job
            profiles={}
            def intern(entry):
                parts,cost=entry;key=hashlib.sha256(json.dumps(parts,separators=(',',':')).encode()).hexdigest()[:16]
                receipt=[parts,cost]
                if key in profiles:assert profiles[key]==receipt
                profiles[key]=receipt;return key
            online={a:intern(fn(a,256)) for a in ARMS}
            upstream=native[q]['arms']['both'];prior=makeops([[['h',v[4]],['s',v[1],v[2]]] for v in upstream]);paid=sum(v[3] for v in upstream)
            assert fn('both',256)==(prior,paid) and paid==bill(tok,prior,src)
            eq={a:[intern(z) for z in equal(fn,'both',a)] for a in ('window','boundary_window')}
            data[q]={'t':t,'info':info,'online':online,'equal':eq,'profiles':profiles}
        print(shard,len(data),flush=True)
    assert set(data)==set(before)
    target=D/f'pred-{shard}.json.gz';return target.name,save(target,data)
def main():
    setup();files=[]
    def known(i):
        p=D/f'pred-{i}.json.gz';r=D/f'receipt-{i}.json'
        if r.exists():
            rec=read(r);assert sha(p)==rec['sha'] and rec['operators']==sha(D/'operator-lock.json');return p.name,rec['sha']
        return None
    needed=[i for i in range(8) if not known(i)]
    with ProcessPoolExecutor(2) as ex:
        for name,dig in ex.map(worker,needed):
            i=int(name.split('-')[1].split('.')[0]);save(D/f'receipt-{i}.json',{'sha':dig,'operators':sha(D/'operator-lock.json')})
    files=[known(i) for i in range(8)];assert all(files)
    n=sum(len(read(D/n)) for n,h in files);assert n==5304
    save(D/'forecast-seal.json',{'files':files,'n':n,'operators':sha(D/'operator-lock.json')})
if __name__=='__main__':main()
