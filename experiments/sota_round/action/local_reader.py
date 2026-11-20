import argparse,json,sys,time,hashlib,re
from pathlib import Path
import torch,transformers
from transformers import AutoTokenizer,AutoModelForCausalLM
def main():
    a=argparse.ArgumentParser();a.add_argument('model',type=Path);a.add_argument('experiment',type=Path);args=a.parse_args()
    m=args.model;root=args.experiment;dest=root/'logs';dest.mkdir(exist_ok=True)
    qs=[json.loads(l) for l in (root/'requests.jsonl').read_text(encoding='utf8').splitlines()]
    system='Use only the supplied task, files and history. Return exactly the requested JSON object, without commentary or markdown.'
    tokenizer=AutoTokenizer.from_pretrained(m,local_files_only=True,padding_side='left')
    model=AutoModelForCausalLM.from_pretrained(m,local_files_only=True,torch_dtype=torch.bfloat16,device_map={'':'cuda:0'},attn_implementation='sdpa').eval()
    model.generation_config.temperature=None;model.generation_config.top_p=None;model.generation_config.top_k=None
    torch.manual_seed(20261116);start=time.monotonic();batchlog=[]
    for k in range(0,len(qs),6):
        batch=qs[k:k+6]
        if all((dest/(r['id']+'.json')).exists() for r in batch):continue
        assert not any((dest/(r['id']+'.json')).exists() for r in batch)
        texts=[tokenizer.apply_chat_template([{'role':'system','content':system},{'role':'user','content':r['prompt']}],tokenize=False,add_generation_prompt=True,enable_thinking=False) for r in batch]
        inputs=tokenizer(texts,padding=True,add_special_tokens=False,return_tensors='pt').to('cuda')
        t=time.monotonic()
        with torch.inference_mode():
            out=model.generate(**inputs,max_new_tokens=1280,do_sample=False,use_cache=True,pad_token_id=tokenizer.pad_token_id)
        torch.cuda.synchronize()
        ee=time.monotonic()-t; gen=out[:,inputs.input_ids.shape[1]:].tolist()
        for j,(r,ids) in enumerate(zip(batch,gen)):
            vals=[]
            for ix in ids:
                if ix in (tokenizer.pad_token_id,tokenizer.eos_token_id):break
                vals.append(ix)
            raw=tokenizer.decode(vals,skip_special_tokens=True,clean_up_tokenization_spaces=False)
            clean=raw.strip();fence=chr(96)*3
            if clean.startswith(fence) and clean.endswith(fence) and '\n' in clean:
                if clean.split('\n',1)[0].lower() in (fence,fence+'json'):clean=clean.split('\n',1)[1][:-3].strip()
            log={'id':r['id'],'status':'ok','model':'Qwen/Qwen3-8B','revision':m.name,'raw':raw,'text':clean,'prompt_sha256':hashlib.sha256(texts[j].encode()).hexdigest(),'usage':{'input_tokens':int(inputs.attention_mask[j].sum()),'output_tokens':len(vals),'cached_input_tokens':0},'at_limit':len(vals)>=1280,'batch':k//6,'batch_seconds':ee}
            (dest/(r['id']+'.json')).write_text(json.dumps(log,ensure_ascii=False,indent=2),encoding='utf8')
        batchlog.append({'batch':k//6,'seconds':ee,'input_width':int(inputs.input_ids.shape[1])});print(k+len(batch),'of',len(qs),'batch',round(ee,1),'s',flush=True)
    (root/'resources.json').write_text(json.dumps({'model':str(m),'revision':m.name,'torch':torch.__version__,'transformers':transformers.__version__,'gpu':torch.cuda.get_device_name(),'python':sys.version,'peak_allocated_bytes':torch.cuda.max_memory_allocated(),'generation_seconds':time.monotonic()-start,'batch_log':batchlog,'system':system,'do_sample':False,'batch_size':6,'max_new_tokens':1280,'thinking':False,'dtype':'bfloat16'},indent=2),encoding='utf8')
if __name__=='__main__':main()

