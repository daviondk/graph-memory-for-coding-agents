"""Open the SQuAD answers only after both window controls and all per-query costs are sealed."""
from collections import Counter
from statistics import mean
import importlib.util
import sys
from data import *
sys.path.insert(0,str(PRIOR))
spec=importlib.util.spec_from_file_location('r26_scoring',PRIOR/'evaluate.py');ev=importlib.util.module_from_spec(spec);spec.loader.exec_module(ev)
from operators import txt,merge
from tokenizers import Tokenizer
def main():
    seal=read(D/'forecast-seal.json');assert seal['n']==5304 and seal['operators']==sha(D/'operator-lock.json')
    forecast={};before={}
    for i,(name,h) in enumerate(seal['files']):
        assert sha(D/name)==h;forecast.update(read(D/name));n,h=read(PRIOR/'choices-lock.json')['files'][i];assert sha(PRIOR/n)==h;before.update(read(PRIOR/n))
    qs=set(forecast);assert qs==set(before)
    gold,quality=ev.true_spans(qs);tok=Tokenizer.from_file(str(TOK))
    by={a['title']:body(a) for a in read(RAW)['data']};rows=[]
    for q,r in sorted(forecast.items()):
        g=gold[q];initial=before[q]
        if not g:continue
        src=by[r['t']];visible=merge([(l,h) for e,l,h in initial['base']]);scores={}
        for key,(ops,charged) in r['profiles'].items():
            s=''.join(txt(p,src) for p in ops);assert len(tok.encode(s,add_special_tokens=False).ids)==charged<=256
            coords=[(p[1],p[2]) for p in ops if p[0]=='s'];allsp=merge([*visible,*coords]);added=merge(coords)
            cov=max(sum(max(0,min(v,h)-max(u,l)) for u,v in allsp)/(h-l) for l,h in g)
            known=sum(max(0,min(a2,b2)-max(a1,b1)) for a1,a2 in visible for b1,b2 in added)
            scores[key]=[int(cov==1),cov,charged,known,sum(v-u for u,v in added),sum(p[0]=='h' for p in ops)]
        online={a:scores[k] for a,k in r['online'].items()};eq={a:[scores[x],scores[y]] for a,(x,y) in r['equal'].items()}
        assert all(x[2]==y[2] for x,y in eq.values())
        assert online['boundary_window'][3]==0
        base=ev.annotate(initial['base'],[],g)[0]
        rows.append({'q':q,'t':r['t'],'initial':base,'cut':bool(initial['cut']),'two_edges':bool(initial['cut'] and initial['cut']['l']>0),'online':online,'equal':eq})
    rows.sort(key=lambda r:r['q'])
    assert len(rows)==5304 and len({r['t'] for r in rows})==442
    def summaries(data):
        return {'hits':sum(x[0] for x in data),'coverage':mean(x[1] for x in data),'mean_paid':mean(x[2] for x in data),'with_known':sum(x[3]>0 for x in data),'empty':sum(x[4]==0 for x in data),'mean_headers':mean(x[5] for x in data),'known_char_fraction':sum(x[3] for x in data)/max(1,sum(x[4] for x in data))}
    def compare(a,mode,panel):
        if mode=='equal':func=lambda r:r['equal'][a][0][0]-r['equal'][a][1][0]
        else:func=lambda r:r['online']['both'][0]-r['online'][a][0]
        return ev.resample(panel,'t',func,263117)
    out={'n':len(rows),'articles':len({r['t'] for r in rows}),'initial_hits':sum(r['initial'] for r in rows),'quality':quality,'online':{a:summaries([r['online'][a] for r in rows]) for a in rows[0]['online']},'full_panel':{},'initial_misses':{},'eq':{},'two_edges':sum(r['two_edges'] for r in rows),'no_component':sum(not r['cut'] for r in rows)}
    for a in ('window','boundary_window'):
        out['eq'][a]=[summaries([r['equal'][a][k] for r in rows]) for k in (0,1)]
        for mode in ('online','equal'):
            out['full_panel'][f'{a}-{mode}']=compare(a,mode,rows)
            out['initial_misses'][f'{a}-{mode}']=compare(a,mode,[r for r in rows if not r['initial']])
    out['rows']=save(D/'outcomes.json.gz',rows);out['forecast']=sha(D/'forecast-seal.json');out['source']=sha(Path(__file__))
    save(D/'results.json',out);print(json.dumps(out['full_panel'],ensure_ascii=False),flush=True)
if __name__=='__main__':main()
