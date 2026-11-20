"""Same published CPU model and tokenization as round 4. Store only blinded cosine ranks."""
import os
os.environ.update(CUDA_VISIBLE_DEVICES="",HF_HUB_OFFLINE="1",TOKENIZERS_PARALLELISM="false")
from common5 import *
import sys,time
sys.path.insert(0,str(E))
from repo_unixcoder import UniXcoder
import torch
torch.set_num_threads(5);torch.set_num_interop_threads(1)
def main():
    assert filehash(D/'blind_new.jsonl.gz')==load(D/'data_lock.json')['blind']
    start=time.monotonic()
    assert filehash(E/'weights/pytorch_model.bin')=='6732b60037b086557e4c731c3748c99b4fec735d9ffe3c4c70061fd142e6b9d9'
    model=UniXcoder(str(E/'weights')).cpu().eval()
    rows=list(rr(D/'blind_new.jsonl.gz'));texts={t for r in rows for t in [*r['queries'].values(),*r['candidates']]}
    ids={t:tuple(model.tokenize([t],mode='<encoder-only>',max_length=512)[0]) if t else () for t in texts}
    vec={():torch.zeros(model.config.hidden_size)}
    seq=sorted(set(ids.values())-{()},key=lambda t:(len(t),t));i=0
    with torch.inference_mode():
        while i<len(seq):
            part=seq[i:i+min(24,max(2,1600//len(seq[i])))]
            padded=torch.full((len(part),max(map(len,part))),model.config.pad_token_id,dtype=torch.long)
            for j,token in enumerate(part):padded[j,:len(token)]=torch.tensor(token)
            _,v=model(padded)
            for t,z in zip(part,v):vec[t]=z.clone()
            i+=len(part)
            if i%100<8 or i==len(seq):print(i,len(seq),round(time.monotonic()-start,1),flush=True)
        outputs=[];near=0;changed=0;single={}
        def one(t):
            if t not in single:single[t]=model(torch.tensor([t]))[1][0].clone() if t else vec[t]
            return single[t]
        for r in rows:
            cs=[ids[c] for c in r['candidates']]
            for k,q in r['queries'].items():
                q=ids[q];scores=[torch.cosine_similarity(vec[q],vec[c],dim=0).item() for c in cs]
                order=sorted(range(len(cs)),key=lambda i:-scores[i])
                if any(cs[a]!=cs[b] and abs(scores[a]-scores[b])<2e-5 for a,b in zip(order,order[1:])):
                    before=order;near+=1;scores=[torch.cosine_similarity(one(q),one(c),dim=0).item() for c in cs];order=sorted(range(len(cs)),key=lambda i:-scores[i]);changed+=int(order!=before)
                outputs.append(dict(panel=r['panel'],idx=r['idx'],query=k,cosine=scores,rank=order))
    jsonrows('new_encoder.jsonl.gz',outputs)
    dump('encoder_receipt.json',dict(utc=now(),unique=len(seq),queries=len(outputs),near=near,changed=changed,seconds=time.monotonic()-start,device='cpu',threads=5,torch=torch.__version__,weights=filehash(E/'weights/pytorch_model.bin'),pred=filehash(D/'new_encoder.jsonl.gz')))
if __name__=='__main__':main()

