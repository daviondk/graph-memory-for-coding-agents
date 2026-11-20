"""Score and seal using input-only files. Run grading separately."""
import gzip
import hashlib
import json
import os
import platform
import statistics
import sys
import time
from pathlib import Path
from collections import Counter

D = Path(__file__).resolve().parent
WORK = D.parent.parent
PRIOR = Path(os.environ.get('PREFIX_REFORMULATION', WORK/'graph_memory_round13'/'reformulation'))
MODEL = Path(os.environ.get('SWERANK_TEMP','D:/CodexResearch/x20-r8-swerank-runtime'))
MANIFEST = WORK/'graph_memory_round8'/'retrieval'
MODEL_REV = '745d2a06103a66d3cfa600aa52fc0d3523010daa'
BACKEND_REV = '92d97331f1f4b6a366c1f161354b9f3390cc219f'
PREFIX = 'Represent this query for searching relevant code: '
PANELS = {'primary':PRIOR, 'replication':PRIOR/'replication'}

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()

def read(path):
    b=path.read_bytes()
    return json.loads(gzip.decompress(b) if path.suffix=='.gz' else b)

def save(path, obj):
    b=json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=None if path.suffix=='.gz' else 2).encode()
    path.write_bytes(gzip.compress(b,mtime=0) if path.suffix=='.gz' else b)

def prepare():
    batches={}
    locks={}
    for panel,path in PANELS.items():
        lock=read(path/'forecast.lock.json')['files']
        uniform=read(path/'uniform.lock.json')
        for name in ['frozen_rankings.json.gz','inputs.json.gz','input.lock.json','rank.py','PROTOCOL_RU.md']:
            assert digest(path/name)==lock[name],(panel,name)
        for name in ['uniform_rankings.json.gz','inputs.json.gz']:
            assert digest(path/name)==uniform[name],(panel,name)
        old={r['id']:r['rank'] for r in read(path/'frozen_rankings.json.gz')}
        uniformr=read(path/'uniform_rankings.json.gz')
        batches[panel]=[]
        for v in read(path/'inputs.json.gz'):
            docs={p:{'body':p+'\n'+o['snip'],'last':o['last']} for p,o in v['docs'].items()}
            id_=v['id']
            ranks=dict(old[id_],uniform=uniformr[id_])
            assert all(len(r)==len(set(r))==len(docs) and set(r)==set(docs) for r in ranks.values())
            batches[panel].append(dict(id=id_,iid=v['iid'],repo=v['repo'],docs=docs,old=ranks,
                q=PREFIX+'Search literal: '+v['key']['literal']+'\nSearch scope: '+v['key']['scope']+'\nIssue: '+v['issue'],
                issue=PREFIX+v['issue']))
        locks[panel]={n:digest(path/n) for n in [*lock,'forecast.lock.json','uniform.lock.json','uniform_rankings.json.gz']}
    return batches,locks

def encode(texts):
    from safetensors.torch import load_file
    import torch
    import transformers
    from transformers import AutoTokenizer
    import numpy as np
    os.environ['CUDA_VISIBLE_DEVICES']=''
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    sys.path.insert(0,str(MODEL))
    from snowflake_cpu.configuration_hf_nomic_bert import NomicBertConfig
    from snowflake_cpu.modeling_hf_nomic_bert import NomicBertModel
    root=MODEL/'model'
    tick=time.perf_counter()
    c=NomicBertConfig.from_json_file(str(root/'config.json'))
    c.use_flash_attn=False
    model=NomicBertModel(c,add_pooling_layer=False)
    model.load_state_dict(load_file(str(root/'model.safetensors')),strict=True)
    model.eval()
    assert next(model.parameters()).device.type=='cpu' and next(model.parameters()).dtype==torch.float32
    tok=AutoTokenizer.from_pretrained(str(root),local_files_only=True)
    meta={'python':platform.python_version(),'torch':torch.__version__,'transformers':transformers.__version__,
        'threads':torch.get_num_threads(),'device':'cpu','compute_dtype':'float32',
        'load_sec':time.perf_counter()-tick, 'text_stats':{},'batch':8,'max_tokens':512}
    vectors={}
    for kind,strings in texts.items():
        order=sorted(set(strings)-set(vectors),key=lambda s:(len(s),s))
        start=time.perf_counter(); truncated=0; token_total=0; padded=0
        for i in range(0,len(order),8):
            chunk=order[i:i+8]
            full=tok(chunk,truncation=False,verbose=False,return_length=True)['length']
            truncated+=sum(n>512 for n in full)
            token_total+=sum(min(n,512) for n in full)
            args=tok(chunk,max_length=512,padding=True,truncation=True,return_tensors='pt')
            padded+=args.input_ids.numel()
            with torch.inference_mode():
                a=torch.nn.functional.normalize(model(**args)[0][:,0],p=2,dim=1).contiguous().cpu().numpy().copy()
            assert np.isfinite(a).all()
            vectors.update(zip(chunk,a))
        meta['text_stats'][kind]={'requested_unique':len(set(strings)),'additional_unique':len(order),'encoded_tokens_unpadded':token_total,'padded_tokens':padded,'truncated_texts':truncated,'sec':time.perf_counter()-start}
        print(kind,meta['text_stats'][kind],flush=True)
    return vectors,meta

def main():
    os.environ['HF_HUB_OFFLINE']='1'
    os.environ['TOKENIZERS_PARALLELISM']='false'
    b,locks=prepare()
    model_hashes=read(MANIFEST/'model_manifest.json')
    for name,obj in model_hashes.items():
        assert digest(MODEL/'model'/name)==obj['sha256']
    backend=read(MANIFEST/'backend_manifest.json')
    assert backend['revision']==BACKEND_REV
    for name,sha in backend['sha256'].items():
        assert digest(MODEL/'snowflake_cpu'/name)==sha
    save(D/'input.lock.json',{'protocol':digest(D/'PROTOCOL_RU.md'),'source':locks,
         'model_revision':MODEL_REV,'model_files':model_hashes,'backend':backend,'source_program':digest(Path(__file__))})
    texts={k:[] for k in ('query','document','path','issue')}
    for panel,rows in b.items():
        for r in rows:
            if r['docs']:
                texts['query'].append(r['q']);texts['issue'].append(r['issue'])
                texts['document'].extend(v['body'] for v in r['docs'].values())
                texts['path'].extend(r['docs'])
    vectors,meta=encode(texts)
    out={};counts={};start=time.perf_counter()
    for panel,rows in b.items():
        pred=[]; stats=Counter(); fresh=[];seen={}
        for r in rows:
            docs=r['docs'];names=sorted(docs); scores={m:{} for m in ('dense','dense_path','dense_issue')}; ranks=dict(r['old'])
            old=seen.setdefault(r['iid'],set())
            ids={o['body'] for o in docs.values()}
            fresh.append(len(ids-old));old.update(ids)
            for p,o in docs.items():
                scores['dense'][p]=float(vectors[r['q']]@vectors[o['body']])
                scores['dense_path'][p]=float(vectors[r['q']]@vectors[p])
                scores['dense_issue'][p]=float(vectors[r['issue']]@vectors[o['body']])
            def order(sc):
                return sorted(names,key=lambda p:(-sc[p],-docs[p]['last'],p))
            for method,sc in scores.items():ranks[method]=order(sc)
            for method in ('strong','graph','shuffled','uniform'):
                a={p:i+1 for i,p in enumerate(ranks['dense'])}; k={p:i+1 for i,p in enumerate(ranks[method])}
                # Rank addition is symmetric even where the two input ranks are reversed.
                ranks['rrf_'+method]=order({p:1/(60+a[p])+1/(60+k[p]) for p in names})
            assert all(len(v)==len(names) and set(v)==set(names) for v in ranks.values())
            stats['empty']+=int(not names);stats['anchors']+=1;stats['pairs']+=len(names)
            pred.append({'id':r['id'],'iid':r['iid'],'repo':r['repo'],'scores':scores,'ranks':ranks})
        out[panel]=pred
        counts[panel]=dict(stats,fresh_document_versions=sum(fresh),median_fresh=statistics.median(fresh),max_fresh=max(fresh))
    meta['rank_sec']=time.perf_counter()-start;meta['counts']=counts
    meta['weight_bytes']=model_hashes['model.safetensors']['size']
    meta['model_package_bytes']=sum(v['size'] for v in model_hashes.values())
    meta['processor']=platform.processor()
    save(D/'predictions.json.gz',out); save(D/'inference.json',meta)
    seal=['PROTOCOL_RU.md','forecast.py','input.lock.json','predictions.json.gz','inference.json']
    save(D/'forecast.lock.json',{n:digest(D/n) for n in seal})
    print(meta['counts'],flush=True)
if __name__=='__main__':main()
