"""Secondary descriptive controls after primary scores, using the previously published nontrivial filter."""
from replicate import HERE,anchor,rows,save,read
import importlib.util
spec=importlib.util.spec_from_file_location('external_eval',HERE/'evaluate.py'); mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);pair=mod.pair
def main():
    items={(r['id'],r['t']):r for r in rows(HERE/'scores.jsonl.gz')}
    slices={'nontrivial':[],'two_or_more_lines':[],'single_line':[]};sources={}
    for k in range(8):
        for task in rows(HERE/f'source_{k}.gz'):
            iid=task['instance'];ev=task['events']
            for t in range(4,len(ev),4):
                if (iid,t) not in items:continue
                q=items[iid,t];a,out=anchor.future_check(ev,t);_,ls=anchor.invert(a,out)
                if any(sum(c.isalnum() for c in s)>=8 for s in ls):slices['nontrivial'].append(q)
                slices['two_or_more_lines' if len(ls)>1 else 'single_line'].append(q)
    out={}
    for k,rows_ in slices.items():
        out[k]=dict(pair=pair(rows_,'cap_address','cap_base'),total=len(rows_),base=sum(r['m']['cap_base'][0] for r in rows_),address=sum(r['m']['cap_address'][0] for r in rows_))
    repos=sorted({q['repo'] for q in items.values()})
    out['loo']={p:pair([q for q in items.values() if q['repo']!=p],'cap_address','cap_base')['delta'] for p in repos}
    save(HERE/'sensitivity.json',out)
    print([(k,v['total'],v['base'],v['address']) for k,v in out.items() if k!='loo'],out['loo'])
if __name__=='__main__':main()
