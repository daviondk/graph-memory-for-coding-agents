import gzip,json
from independent import D,INPUT,KEYS,read,save,sha
out={}
for p in ('D','E'):
    theirs=read(INPUT/(p+'_items.json.gz'));ours={r['id']:r for r in (json.loads(s) for s in gzip.open(D/f'{p}_independent_rows.jsonl.gz','rt'))}
    n=0;max_err=0.
    assert set(ours)=={r['id'] for r in theirs}
    for row in theirs:
        for method,cases in row['m'].items():
            for j,key in enumerate(KEYS):
                x=ours[row['id']][method][j];y=cases[key]/(100 if key=='es' else 1)
                err=abs(x-y);max_err=max(err,max_err);assert err<1e-12,(p,row['id'],key,x,y)
                n+=1
    out[p]=dict(matched_values=n,max_abs_error=max_err,parent_input_sha=sha(INPUT/(p+'_items.json.gz')))
save('verified_parent.json',out);print(out)

