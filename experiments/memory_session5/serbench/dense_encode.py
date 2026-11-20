"""Run inside the CUDA PyTorch environment after the Qwen tests release the GPU."""
import os
os.environ['HF_HUB_OFFLINE']='1';os.environ['TOKENIZERS_PARALLELISM']='false'
from pathlib import Path
import gzip,hashlib,json,platform,sys,time
import numpy as np
import torch,transformers
from transformers import AutoTokenizer,AutoModel
ROOT=Path(__file__).resolve().parent
def main():
    modelpath=ROOT/'weights';texts=[json.loads(l) for l in gzip.open(ROOT/'dense_texts.jsonl.gz','rt',encoding='utf-8')]
    assert all(hashlib.sha256(t['text'].encode()).hexdigest()==t['sha256'] for t in texts)
    tk=AutoTokenizer.from_pretrained(modelpath,local_files_only=True)
    model=AutoModel.from_pretrained(modelpath,local_files_only=True,torch_dtype=torch.float16,attn_implementation='sdpa').to('cuda').eval()
    start=time.time();arr=[]
    for i in range(0,len(texts),128):
        res=tk([t['text'] for t in texts[i:i+128]],truncation=True,max_length=512,padding=False)
        arr.extend(res['input_ids'])
    order=sorted(range(len(texts)),key=lambda i:len(arr[i]))
    vectors=ROOT/'dense_vectors.npy';marker=ROOT/'dense_progress.json'
    resume=json.loads(marker.read_bytes()) if marker.exists() else None
    identity=hashlib.sha256(('\n'.join(t['sha256'] for t in texts)).encode()).hexdigest()
    if resume:
        assert resume['input_content_sha']==identity
        vec=np.load(vectors,mmap_mode='r+');cursor=resume['cursor']
    else:
        vec=np.lib.format.open_memmap(vectors,mode='w+',dtype=np.float16,shape=(len(texts),model.config.hidden_size));cursor=0
    torch.set_num_threads(3)
    with torch.inference_mode():
        while cursor<len(order):
            batch=order[cursor:cursor+48]
            maxlen=max(len(arr[i]) for i in batch);pad=tk.pad_token_id
            batchids=[arr[i]+[pad]*(maxlen-len(arr[i])) for i in batch];attn=[[1]*len(arr[i])+[0]*(maxlen-len(arr[i])) for i in batch]
            hidden=model(input_ids=torch.tensor(batchids,device='cuda'),attention_mask=torch.tensor(attn,device='cuda')).last_hidden_state[:,0,:].float()
            emb=torch.nn.functional.normalize(hidden,dim=1)
            assert torch.isfinite(emb).all()
            vec[batch]=emb.cpu().numpy().astype('float16');cursor+=len(batch)
            if cursor%480==0 or cursor==len(order):
                vec.flush();tmp=marker.with_suffix('.tmp')
                tmp.write_text(json.dumps({'input_content_sha':identity,'cursor':cursor,'count':len(order),'seconds_current_process':time.time()-start}))
                tmp.replace(marker)
                if cursor%2400==0:print('encoded',cursor,'of',len(order),'seconds',round(time.time()-start,1),flush=True)
    with vectors.open('rb') as f:sha=hashlib.sha256()
    with vectors.open('rb') as f:
        for block in iter(lambda:f.read(2**20),b''):sha.update(block)
    (ROOT/'dense_runtime.json').write_text(json.dumps({'python':sys.version,'torch':torch.__version__,'transformers':transformers.__version__,'gpu':torch.cuda.get_device_name(0),'peak_alloc_MiB':torch.cuda.max_memory_allocated()/2**20,'max_seq':512,'vector_dtype':'float16','weights_dtype':'float16','hidden':vec.shape[1],'count':len(order),'vectors_sha256':sha.hexdigest(),'seconds':time.time()-start,'input_seq_tokens':sum(map(len,arr))},indent=2))
if __name__=='__main__':main()
