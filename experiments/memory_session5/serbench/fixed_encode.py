"""Encode the 2500 length-controlled queries with the identical pretrained reader."""
from dense_encode import ROOT,torch,AutoModel,np,json,gzip,time
def main():
    torch.set_num_threads(3);model=AutoModel.from_pretrained(ROOT/'weights',local_files_only=True,torch_dtype=torch.float16,attn_implementation='sdpa').to('cuda').eval()
    rows=[json.loads(x) for x in gzip.open(ROOT/'fixed_queries.jsonl.gz','rt')]; seq=[z for r in rows for z in r['ids'].values()]
    vec=np.empty((len(seq),model.config.hidden_size),np.float16)
    order=sorted(range(len(seq)),key=lambda i:len(seq[i]));start=time.time()
    with torch.inference_mode():
        for off in range(0,len(order),48):
            ix=order[off:off+48];L=max(len(seq[i]) for i in ix)
            inp=torch.tensor([seq[i]+[0]*(L-len(seq[i])) for i in ix],device='cuda')
            mask=torch.tensor([[1]*len(seq[i])+[0]*(L-len(seq[i])) for i in ix],device='cuda')
            y=model(input_ids=inp,attention_mask=mask).last_hidden_state[:,0,:].float()
            vec[ix]=torch.nn.functional.normalize(y,dim=1).cpu().numpy().astype(np.float16)
    assert np.isfinite(vec).all()
    np.save(ROOT/'fixed_vectors.npy',vec);print(len(vec),'queries',time.time()-start,'s')
if __name__=='__main__':main()
