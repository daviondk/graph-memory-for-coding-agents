"""Reconstruct every sealed packet's observed precondition and verify all score entries offline."""
import collections,gzip,hashlib,json,sys
from pathlib import Path
from common import ROOT,rows,advance,newmeta,pages,digest,groups,rel
from policy import BUDGETS,render,cost
from pipeline import future,snapshots
def load(p):return json.loads(p.read_bytes())
def verify_filemap(m,root=ROOT):
    for f,x in m.items():assert digest(root/f)==x,f
def independent_hit(picks,path,old):
    # Reconstruct contiguous lines by coordinates. More than one exact occurrence is ambiguous.
    lines={}
    for name,lo,hi,_,txt in picks:
        if name!=path:continue
        vals=txt.split('\n');assert len(vals)==hi-lo+1
        for n,v in enumerate(vals,lo):
            assert n not in lines;lines[n]=v
    count=0
    for nums in groups(lines):
        txt='\n'.join(lines[n] for n in nums);j=txt.find(old)
        if j>=0:
            if txt.find(old,j+1)>=0:return False
            count+=1
    return count==1
def replay(folder,sources,expect,tokenize):
    counts=collections.Counter();hits=collections.Counter();total_tokens=collections.Counter()
    for k in range(8):
        pred=iter(rows(folder/'sealed'/f'{k}.jsonl.gz'));scored=iter(rows(folder/'metrics'/f'{k}.jsonl.gz'))
        for item in rows(sources/f'{k}.jsonl.gz'):
            counts['tasks']+=1
            assert int(hashlib.sha256(('compact-s4|'+item['instance']).encode()).hexdigest(),16)%10!=0
            for t,ss,m in snapshots(item):
                id_,cut,ds=next(pred);assert id_==item['instance'] and cut==t
                counts['cuts']+=1;tar=future(item['events'],t);obs={k:pages(v) for k,v in ss.items()}
                if tar:
                    gold=next(scored);counts['intents']+=1;counts['accepted']+=int(tar[2])
                    assert (gold['id'],gold['cut'],gold['accepted'],gold['old_sha'])==(id_,t,tar[2],hashlib.sha256(tar[1].encode()).hexdigest())
                for b,rs in ds.items():
                    for a,(ids,tok) in rs.items():
                        pg=obs['drop' if a=='reset_tail' else 'rebase'];assert len(ids)==len(set(ids)) and all(0<=i<len(pg) for i in ids)
                        picks=[pg[i] for i in ids];assert 0<=tok<=int(b)
                        if tokenize:assert cost('\n'.join(render(v) for v in picks))==tok
                        if tar:
                            mark=independent_hit(picks,tar[0],tar[1])
                            assert gold['metrics'][b][a]==[int(mark),tok]
                            if tar[2]:hits[b,a]+=mark;total_tokens[b,a]+=tok
        assert next(pred,None) is None and next(scored,None) is None
    assert dict(counts)==expect,(counts,expect)
    return counts,hits,total_tokens
def main():
    tok='--tokens' in sys.argv;T=ROOT/'transfer'
    verify_filemap(load(ROOT/'fit_lock.json'));verify_filemap(load(ROOT/'prediction_lock.json')['files'])
    verify_filemap(load(T/'fit_lock.json'),T);verify_filemap(load(T/'method_lock.json'))
    for split in ['train','test']:verify_filemap(load(T/split/'predictions_lock.json'))
    a,h1,c1=replay(ROOT,ROOT/'source/test',load(ROOT/'coverage.json'),tok)
    tr,htr,ctr=replay(T/'train',ROOT/'source/test',load(T/'train/coverage.json'),tok)
    b,h2,c2=replay(T/'test',T/'source',load(T/'test/coverage.json'),tok)
    stats=load(ROOT/'results.json')['results'];s2=load(T/'results.json')['results']
    for (budget,arm),v in h1.items():assert stats[budget]['metrics'][arm]=={'hit':v,'average_tokens':c1[budget,arm]/a['accepted']}
    for (budget,arm),v in h2.items():assert s2[budget]['B_metrics'][arm]=={'hit':v,'mean_tokens':c2[budget,arm]/b['accepted']}
    for (budget,arm),v in htr.items():assert s2[budget]['A_posthoc_comparator_hits'][arm]==v
    groups=[]
    for path in (ROOT/'source/train',ROOT/'source/test',T/'source'):
        cases=[r['instance'] for k in range(8) for r in rows(path/f'{k}.jsonl.gz')]
        assert len(cases)==len(set(cases));groups.append(set(cases))
    assert all(not x&y for j,x in enumerate(groups) for y in groups[j+1:])
    repos=[{i.split('.')[0] for i in g} for g in groups];assert not repos[0]&repos[1] and not repos[2]&repos[1]
    print('PASS',dict(a),dict(b),'disjoint sets',list(map(len,groups)),'repos',list(map(len,repos)),'native tokenizer verification',tok)
if __name__=='__main__':main()
