"""Apply the same calendar and speaker projection to flat and graph top-five lists."""
from transfer_reader import date,grounded,rewrite
from emb import session,batch
from prepare import P,read,write,sha
from evaluate import aggregate,official,normalized
from score_transfer import compare
import json,gzip,time,numpy as np
def main():
    lock=read('transfer_lock.json');ids=set(lock['items']); ranks=json.loads(gzip.decompress((P/'predictions.json.gz').read_bytes()))
    old=read('transfer_output.json');pending={};mapping={};saved={};data=read('input.json');t0=time.time()
    for c in data:
        ts={t['id']:t for t in c['turns']};people=sorted({x['speaker'] for x in ts.values()})
        for q in c['queries']:
            i=q['id']
            if i not in ids:continue
            for a in ('date','joint'):
                for system in ['flat','graph']:
                    arm=system+'_'+a;chunks=[]
                    for u in ranks[i][system][0][:5]:
                        t=ts[u];s=t['speaker'];o=next(p for p in people if p!=s)
                        text=rewrite(t['text'],s,o) if a=='joint' else t['text']
                        text=grounded(text,date(t['time']));chunks.append(t['time']+" | "+s+": "+text+(" (Image: "+t['caption']+")" if t['caption'] else ''))
                    ctx='\n'.join(chunks);key=sha(q['text']+'\n'+ctx);mapping.setdefault(i,{})[arm]=key
                    if system=='graph':saved[key]=old[i][a]
                    else:pending[key]=(q['text'],ctx)
    pending={k:v for k,v in pending.items() if k not in saved};order=sorted(pending,key=lambda k:(len(pending[k][1]),k));so,tok=session('reader')
    write('matched_reader_lock.json',dict(protocol=sha((P/'MATCHED_READER.md').read_bytes()),script=sha((P/'matched_reader.py').read_bytes()),input_sha=lock['upstream_predictions'],n=len(ids),new_forward=len(order)))
    for lo in range(0,len(order),8):
        bucket=order[lo:lo+8];enc=tok.encode_batch([pending[key] for key in bucket]);(st,en),mask=batch(so,enc)
        for j,(key,v) in enumerate(zip(bucket,enc)):
            eligible=np.array([s==1 for s in v.sequence_ids]);best=-1e12;S=E=None
            for width in range(1,25):
                score=st[j,:len(eligible)-width+1]+en[j,width-1:];ok=eligible[:len(score)]&eligible[width-1:];vi=np.where(ok,score,-1e20);l=int(np.argmax(vi))
                if vi[l]>best:best=float(vi[l]);S=l;E=l+width-1
            assert S is not None;saved[key]=dict(answer=pending[key][1][v.offsets[S][0]:v.offsets[E][1]],tokens=int(mask[j].sum()),truncated=bool(v.overflowing))
    out={i:{a:saved[k] for a,k in arms.items()} for i,arms in mapping.items()};write('matched_reader_output.json',out)
    gold=read('gold.json');rows={i:{a:dict(f1=official(x['answer'],gold[i]['answer'],gold[i]['cat']),em=int(normalized(x['answer'])==normalized(gold[i]['answer'])),tokens=x['tokens']) for a,x in arms.items()} for i,arms in out.items()}
    write('matched_reader_results.json',dict(n=len(out),means=aggregate(rows),graph_minus_flat={a:compare(rows,'graph_'+a,'flat_'+a,'f1') for a in ('joint','date')},new_forward=len(order),wall_seconds=time.time()-t0,sha=sha((P/'matched_reader_output.json').read_bytes())))
if __name__=='__main__':main()