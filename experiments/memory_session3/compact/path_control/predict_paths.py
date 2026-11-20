import gzip,json,sys,time
from pathlib import Path
from collections import defaultdict
from itertools import chain
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
from e3_predict import add
from token_predict import fit,token_count
from predict import author,sha_bytes,dumps

def unique(parts):
    return list(dict.fromkeys(chain.from_iterable(parts)))

def main():
    starts=time.perf_counter();hist=defaultdict(list); n=0
    with gzip.open(ROOT/'prefixes.jsonl.gz','rt',encoding='utf8') as inp,gzip.open(ROOT/'predictions.jsonl.gz','wt',encoding='utf8') as f:
        for ln in inp:
            x=json.loads(ln);i,j=x['i'],x['j'];s=x['summary']; prev=hist[i]
            assert len(prev)==j
            if j:
                cap=token_count(s)
                anchors=sorted({(t,v) for old,_ in prev for t,vs in author.atoms_in_text(old).items() for v in vs if v not in s})
                paths=[a for a in anchors if a[0]=='path']
                other=[a for a in anchors if a[0]!='path']
                done=unique([ [('path',v) for v in sorted(writes) if v and v not in s] for _,writes in [(s,x['writes']),*reversed(prev)] ])
                plans={'paths':paths,'paths_then_other':paths+other,'write_paths':unique([done,paths]),'write_paths_then_other':unique([done,paths,other]),'writes_only':done}
                for name,order in plans.items():
                    items,extra=fit(order,cap//10,token_count,True)
                    out=add(s,extra,cap)
                    used=token_count(out)
                    assert used<=cap
                    f.write(dumps({'i':i,'j':j,'arm':name,'S':out,'cap':cap,'used':used,'extra_tokens':token_count(extra),'items':items})+'\n')
                    n+=1
            prev.append((s,x['writes']))
    names=['PROTOCOL.md','prefixes.jsonl.gz','predict_paths.py','predictions.jsonl.gz','../e3_predict.py','../token_predict.py','../source/qwen_tokenizer.json','../source/cb_common.py']
    (ROOT/'lock.json').write_text(json.dumps({'sha256':{n:sha_bytes((ROOT/n).read_bytes()) for n in names},'predictions':n,'wall_s':time.perf_counter()-starts},indent=1),encoding='utf8')
if __name__=='__main__':main()

