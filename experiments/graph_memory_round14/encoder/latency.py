"""Small fixed, outcome-blind live CPU latency probe with warm weights."""
from collections import defaultdict
import hashlib
import os
import statistics
import sys
import time
from forecast import D,MODEL,PANELS,prepare,save,read

def strata(n):
    return 0 if n==1 else 1 if n<=3 else 2 if n<=8 else 3
def main():
    import numpy as np
    import torch
    from transformers import AutoTokenizer
    from safetensors.torch import load_file
    os.environ['CUDA_VISIBLE_DEVICES']=''
    os.environ['TOKENIZERS_PARALLELISM']='false'
    torch.set_num_threads(4);torch.set_num_interop_threads(1)
    sys.path.insert(0,str(MODEL))
    from snowflake_cpu.configuration_hf_nomic_bert import NomicBertConfig
    from snowflake_cpu.modeling_hf_nomic_bert import NomicBertModel
    c=NomicBertConfig.from_json_file(str(MODEL/'model'/'config.json'));c.use_flash_attn=False
    model=NomicBertModel(c,add_pooling_layer=False);model.load_state_dict(load_file(str(MODEL/'model'/'model.safetensors')),strict=True)
    model.eval()
    tok=AutoTokenizer.from_pretrained(str(MODEL/'model'),local_files_only=True)
    @torch.inference_mode()
    def emb(seq):
        toks=tok(seq,max_length=512,padding=True,truncation=True,return_tensors='pt')
        return torch.nn.functional.normalize(model(**toks)[0][:,0],p=2,dim=1).numpy().copy()
    b,_=prepare()
    rows=[];costs={}
    emb(['Locate the code in memory.'])
    for panel,items in b.items():
        select=defaultdict(list)
        for r in items:
            if r['docs']:select[strata(len(r['docs']))].append(r)
        quotas=[2,2,2,1] if panel=='primary' else [1,1,1,2]
        for group,quota in enumerate(quotas):
            order=sorted(select[group],key=lambda r:hashlib.sha256(r['id'].encode()).hexdigest())
            for r in order[:quota]:
                names=sorted(r['docs']);body=[r['docs'][p]['body'] for p in names]
                t=time.perf_counter_ns();q=emb([r['q']])[0];qq=time.perf_counter_ns()
                arr=np.concatenate([emb(body[i:i+8]) for i in range(0,len(body),8)])
                tdoc=time.perf_counter_ns()
                vals=arr@q
                score=dict(zip(names,vals))
                rank=sorted(names,key=lambda p:(-score[p],-r['docs'][p]['last'],p))
                tscore=time.perf_counter_ns()
                rows.append({'panel':panel,'id':r['id'],'n':len(names),'q_ms':(qq-t)/1e6,
                         'all_documents_ms':(tdoc-qq)/1e6,'score_sort_ms':(tscore-tdoc)/1e6,'first':rank[0]})
        d=PANELS[panel]
        import importlib.util
        sp=importlib.util.spec_from_file_location('baseline_'+panel,d/'rank.py');base=importlib.util.module_from_spec(sp);sp.loader.exec_module(base)
        stored=read(d/'inputs.json.gz');tt=[]
        for repeat in range(3):
            t=time.perf_counter()
            for r in stored:
                _,m=base.calculate(r)
                tt.append((m['prepare_ns']/1e6,m['graph_ns']/1e6))
        costs[panel]={'n':len(stored),'repeats':3,'mean_strong_ms':statistics.mean(x[0] for x in tt),
                'mean_graph_increment_ms':statistics.mean(x[1] for x in tt),'median_graph_increment_ms':statistics.median(x[1] for x in tt)}
    save(D/'latency.json',{'cpu':'same warm CPU batch 1 for query; 8 maximum per document batch','cases':rows,'counts':len(rows),'graph':costs})
    print('latency cases',len(rows),flush=True)
if __name__=='__main__':main()
