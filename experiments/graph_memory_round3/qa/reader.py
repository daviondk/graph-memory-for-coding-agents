"""Answer the same metadata-selected 350 questions from each policy's frozen five original turns."""
import gzip,json,time,collections
import numpy as np
from emb import session,batch
from prepare import P,read,write,sha
def main():
    ranks=json.loads(gzip.decompress((P/'predictions.json.gz').read_bytes()));lock=read('prediction_lock.json')
    assert sha((P/'predictions.json.gz').read_bytes())==lock['sha256']['predictions.json.gz']
    data=read('input.json');g=read('gold.json');pool={};mapping={};subset=[]
    arms=['bm25','fusion','flat','graph','placebo']
    for c in data:
        turns={t['id']:t for t in c['turns']};chosen=[]
        for q in c['queries']:
            ann=g[q['id']]
            if ann['cat'] in [1,2,3,4] and ann['evidence'] and set(ann['evidence'])<=set(turns):chosen.append(q)
        for q in sorted(chosen,key=lambda q:sha('r3-reader|'+q['id']))[:35]:
            i=q['id'];subset.append(i);mapping[i]={}
            for a in arms:
                ids=ranks[i][a][0][:5]
                def render(t):
                    return str(t['time'])+" | "+t['speaker']+": "+t['text']+(" (Image: "+t['caption']+")" if t['caption'] else '')
                ctx="\n".join(render(turns[j]) for j in ids)
                key=sha(q['text']+"\n"+ctx);mapping[i][a]=key;pool[key]=(q['text'],ctx)
    write('reader_lock.json',{"input_sha":sha((P/'predictions.json.gz').read_bytes()),"reader_code":sha((P/'reader.py').read_bytes()),"questions":subset,"arms":arms})
    so,tok=session('reader');started=time.time()
    # Only the first truncation window enters the actual reading pass; per-record lengths are logged.
    out={};order=sorted(pool,key=lambda k:(len(pool[k][1]),k))
    for lo in range(0,len(order),8):
        bucket=order[lo:lo+8];enc=tok.encode_batch([pool[key] for key in bucket]);(st,en),mask=batch(so,enc)
        for j,(k,v) in enumerate(zip(bucket,enc)):
            eligible=np.array([s==1 for s in v.sequence_ids]);best=-1e12;S=E=None
            for width in range(1,25):
                score=st[j,:len(eligible)-width+1]+en[j,width-1:]
                ok=eligible[:len(score)]&eligible[width-1:];vi=np.where(ok,score,-1e20)
                l=int(np.argmax(vi))
                if vi[l]>best:best=float(vi[l]);S=l;E=l+width-1
            assert S is not None
            text=pool[k][1][v.offsets[S][0]:v.offsets[E][1]];out[k]=dict(answer=text,tokens=int(mask[j].sum()),truncated=bool(v.overflowing),span=[v.offsets[S][0],v.offsets[E][1]])
    write("reader_output.json",{i:{a:out[k] for a,k in seen.items()} for i,seen in mapping.items()})
    write("reader_receipt.json",dict(physical_calls=len(pool),logical_calls=sum(map(len,mapping.values())),unique_questions=len(mapping),seconds=time.time()-started,provider=so.get_providers(),reader_sha=sha((P/'reader_output.json').read_bytes()),tokens=sum(x['tokens'] for x in out.values())))
if __name__=='__main__':main()