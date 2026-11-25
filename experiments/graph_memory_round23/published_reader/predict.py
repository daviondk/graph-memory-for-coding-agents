"""Run the authors' pinned process() twice per source unit and seal typed selections."""
from inputs import *
from time import perf_counter
import platform
os.environ.update(CUDA_VISIBLE_DEVICES='',HF_HOME=str(PRIVATE/'hub'),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TORCHDYNAMO_DISABLE='1')
import torch
import transformers
from transformers import AutoModel
from tokenizers import Tokenizer
ARMS=('whole','parent','fine','verbatim','verbatim_core','verbatim_fill','verbatim_recall_core')
def union(spans):
    out=[]
    for a,b in sorted(map(tuple,spans)):
        if out and a<=out[-1][1]:out[-1][1]=max(out[-1][1],b)
        else:out.append([a,b])
    return out
def subtract(a,b,covered):
    res=[]
    for u,v in covered:
        if v<=a:continue
        if u>=b:break
        if a<u:res.append((a,min(u,b)))
        a=max(a,v)
    if a<b:res.append((a,b))
    return res
def render(rows,fields,tok):
    coverage=defaultdict(list);context='';spans=[];paid=0
    for e,a,b in rows:
        novel=subtract(a,b,coverage[e])
        if not novel:continue
        txt='\n'.join(fields[str(e)][u:v] for u,v in novel)
        candidate=context+'\n'+txt if context else txt
        encoded=tok.encode(candidate,add_special_tokens=False)
        if len(encoded.ids)>2048:continue
        context=candidate;paid=len(encoded.ids)
        coverage[e]=union([*coverage[e],*novel]);spans.extend([[e,u,v] for u,v in novel])
    assert context=='\n'.join(fields[str(e)][a:b] for e,a,b in spans)
    assert paid==len(tok.encode(context,add_special_tokens=False).ids)<=2048
    return {'tokens':paid,'spans':spans,'context_sha':h(context.encode())}
def reader():
    torch.set_num_threads(2);torch.set_num_interop_threads(1)
    m=AutoModel.from_pretrained(MODEL,trust_remote_code=True,local_files_only=True,
                                reference_compile=False,attn_implementation='eager').to('cpu').eval()
    assert type(m).__name__=='VerbatimRagHighlighter' and not torch.cuda.is_initialized()
    return m,m._get_tokenizer(),Tokenizer.from_file(str(E5))
def predict(stage):
    inputs=load(HERE/f'{stage}-inputs.json');plan=load(HERE/'plan.json')
    assert inputs['plan']==sha(HERE/'plan.json') and sha(MODEL/'model.safetensors')==WEIGHT
    if stage=='test':assert load(HERE/'dev-seal.json')['n']==4
    code=sha(Path(__file__));input_sha=sha(HERE/f'{stage}-inputs.json')
    model,tokenizer,e5=reader();receipts={}
    for it in plan['selection'][stage]:
        q=it['q'];info=inputs['subset'][q];path=PRIVATE/stage/f'{q[6:]}.json.gz'
        out=HERE/'forecasts'/stage/f'{q[6:]}.json.gz'
        if out.exists():
            already=load(out);assert already['input']==info['sha'] and already['code']==code
            receipts[q]=sha(out);continue
        assert sha(path)==info['sha'];s=load(path);parents=s['parents'];fields=s['fields'];query=s['query']
        scored=[[],[]];diagnostic=[];total=[0.,0.]
        for j,(e,a,b) in enumerate(parents):
            context=fields[str(e)][a:b]
            length=len(tokenizer(query,context,verbose=False)['input_ids'])
            enc=tokenizer(query,context,return_offsets_mapping=True,max_length=8192,truncation='only_second',stride=256,return_overflowing_tokens=True)
            covered=[]
            for wi in range(len(enc['input_ids'])):
                covered.extend([(l,h) for (l,h),sid in zip(enc['offset_mapping'][wi],enc.sequence_ids(wi),strict=True) if sid==1 and h>l])
            source_offsets=tokenizer(context,add_special_tokens=False,return_offsets_mapping=True)['offset_mapping']
            assert set(source_offsets)<=set(covered)|{(0,0)}
            stats=[]
            for k,(thr,mn) in enumerate(((.2,30),(.1,10))):
                tic=perf_counter()
                result=model.process(question=query,context=context,threshold=thr,min_span_chars=mn)
                elapsed=perf_counter()-tic;total[k]+=elapsed
                values=result['spans']
                for span in values:
                    l,hi=float(span['start']),float(span['end']);assert l.is_integer() and hi.is_integer()
                    l,hi=int(l),int(hi);prob=span['score']
                    assert 0<=l<hi<=len(context) and span['text']==context[l:hi] and 0<=prob<=1
                    scored[k].append((-prob,j,l,[e,a+l,a+hi]))
                stats.append([len(values),elapsed])
            diagnostic.append([j,length,len(enc['input_ids']),*stats])
        order=[[x[-1] for x in sorted(arr)] for arr in scored]
        core=parents[:2]
        blocks=s['blocks']
        fine=[r[:3] for _,r in sorted(enumerate(blocks),key=lambda zr:(-zr[1][5],zr[0]))]
        by_parent=[r[:3] for _,r in sorted(enumerate(blocks),key=lambda zr:(zr[1][4],zr[0]))]
        options={'whole':parents,'parent':core+by_parent,'fine':core+fine,'verbatim':order[0],
                 'verbatim_core':core+order[0],'verbatim_fill':core+order[0]+parents,
                 'verbatim_recall_core':core+order[1]}
        tic=perf_counter();answers={name:render(options[name],fields,e5) for name in ARMS};pack_time=perf_counter()-tic
        save(out,{'q':q,'t':s['t'],'i':s['i'],'ad':s['ad'],'parent_spans':parents,'picks':answers,
                  'inferences':diagnostic,'elapsed_default':total[0],'elapsed_recall':total[1],
                  'elapsed_pack_all':pack_time,'input':info['sha'],'code':code})
        receipts[q]=sha(out);print(stage,len(receipts),q,round(sum(total),2),flush=True)
    save(HERE/f'{stage}-seal.json',{'n':len(receipts),'files':receipts,'inputs':input_sha,'code':code,
                                    'torch':torch.__version__,'transformers':transformers.__version__,
                                    'python':sys.version,'device':'cpu','threads':2,'backend':'eager reference_compile=False','platform':platform.platform()})
if __name__=='__main__':predict(sys.argv[1])
