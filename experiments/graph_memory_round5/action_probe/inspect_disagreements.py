"""Trace attribution for previously recorded disagreements. No trace commands execute."""
from pathlib import Path
import importlib.util,re,sys,shlex
spec=importlib.util.spec_from_file_location('r5_probe_policy',Path(__file__).with_name('policy.py'));pol=importlib.util.module_from_spec(spec);spec.loader.exec_module(pol)
from collections import defaultdict
D,W,rr,save,token,anchor=pol.D,pol.W,pol.rr,pol.save,pol.token,pol.anchor
def main():
    bad=defaultdict(list)
    for iid,repo,at,arm,p,n,ok in rr(D/'neighbors.jsonl.gz'):
        if arm=='address' and not ok:bad[iid,at,p].append(n)
    raw_by=dict(rr(D/'raw_pairs.jsonl.gz'));delta=defaultdict(list)
    for iid,j,changes in rr(D/'decisions.jsonl.gz'):
        if any(iid==key[0] for key in bad):delta[iid].append(changes['address'])
    reports=[]
    for q in (q for sh in range(8) for q in rr(W/f'source_{sh}.jsonl.gz')):
        iid=q['instance']
        for (case,at,p),numbers in bad.items():
            if case!=iid:continue
            root=True;actual={};state={};add=defaultdict(list);ops=[]
            for j,(e,r,c) in enumerate(zip(q['events'],raw_by[iid],delta[iid]),1):
                name,args,obs=e
                if j==at:
                    first,block,pos=anchor.unique_new(args,obs);lo=first+block[:pos].count('\n');end=lo+args['new_str'].count('\n');shift=args['new_str'].count('\n')-args['old_str'].count('\n')
                    doc={n if n<lo else n-shift:token(s) for n,s in anchor.printed(obs).items() if not lo<=n<=end}
                    for n in numbers:
                        z=state[p,n];v=doc[n];src=[x for x in add.get((p,n),[]) if x[1]==z]
                        sameline=[other-n for other,sv in doc.items() if sv==z]
                        neighbor=[other-n for (path,other),sv in state.items() if path==p and sv==v and abs(other-n)<=20]
                        actual[n]=dict(last_add=src[-1] if src else None,old_sha=z,truth_sha=v,memory_matching_truth_offsets=neighbor,editor_matching_old_offsets=sameline)
                    break
                lines=pol.readlines(r,root)
                for f,n,s,method in lines:add[f,n].append([j,token(s),method])
                a=(r or {}).get('command','')
                if r:
                    if re.search(r'(?:^|[;&\n])\s*(?:cd|pushd|popd)\b',a):root=False
                    if re.fullmatch(r'\s*cd\s+/testbed/?\s*',a):root=True
                if r or args.get('path','').endswith(p):
                    try:head=shlex.split(a)[0] if a else args.get('command','')
                    except ValueError:head='complex'
                    ops.append(dict(step=j,name=head,mentions_path=p in a or args.get('path','').endswith(p),mentions_leaf=Path(p).name in a,write_indicators=sorted(set(re.findall(r'\b(?:write_text|write_bytes|replace|open|sed|patch|git|checkout|apply|pathlib|mv|cp|rename|str_replace_editor)\b',a))),redirect=bool(re.search(r'>>?',a)),success=anchor.success(args.get('command'),p,obs),accepted_here=sum(f==p for f,n,s,m in lines)))
                for f,n,s in c:
                    if s is None:state.pop((f,n),None)
                    else:state[f,n]=s
            reports.append(dict(instance=case,step=at,path=p,observations=actual,intermediate=ops))
    save('disagreements.json',reports)
if __name__=='__main__':main()

