"""Post-score, descriptive diagnostics. No changes to predictions or primary estimands."""
import collections,itertools
from common import *
def main():
    d=read('score_vectors.json.gz')['reader']['clean'];out={}
    for key in ('latest','witness'):
        vals=d['values'][key];base=d['values']['empty'];by=collections.defaultdict(list)
        for group,x,y in zip(d['groups'],vals,base):by[group].append(x-y)
        sums=[sum(ds) for ds in by.values()];actual=abs(sum(sums))
        tail=sum(abs(sum(x*s for x,s in zip(sums,signs)))>=actual-1e-12 for signs in itertools.product((-1,1),repeat=len(sums)))
        out[key]={'difference_histogram':dict(collections.Counter(str(x-y) for x,y in zip(vals,base))),
                  'repository_details':{k:{'n':len(v),'effect_sum':sum(v)} for k,v in sorted(by.items())},
                  'exploratory_repository_signflip_p':tail/2**len(sums),
                  'assumptions':'Sign-flip diagnostic assumes symmetric independent repository effects. No familywise adjustment. Small number of repositories limits inference.'}
    write('diagnostics.json',out);print(canon(out))
if __name__=='__main__':main()
