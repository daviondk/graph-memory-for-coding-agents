import gzip,hashlib,json,statistics,time
from pathlib import Path
import torch
from transformers import AutoTokenizer,AutoModelForSequenceClassification
p=Path('D:/CodexResearch/x20-boundary-rerank/model');root=Path('D:/CodexResearch/x20-bench-workspace/work/graph_memory_round22/native_multiseed/official580')
pri=Path('D:/CodexResearch/x20-native-multiseed/official580/dev')
def read(p):return json.loads(gzip.decompress(p.read_bytes()))
def h(x):return hashlib.sha256(x).hexdigest()
torch.set_num_threads(2);torch.set_num_interop_threads(1)
tok=AutoTokenizer.from_pretrained(p,local_files_only=True);m=AutoModelForSequenceClassification.from_pretrained(p,local_files_only=True).eval()
ids=sorted(read(root/'split.json.gz')['dev'],key=lambda r:h(('r23-ce-scope|'+r['q']).encode()))[:8]
pairs=[]
for it in ids:
    row=read(pri/(it['t']+'.json.gz'));query=dict(row['q'])[it['q']]
    nodes=sorted((n for n in row['g']['nodes'] if n['kind'] in ('content.tool_output','content.tool_argument')),key=lambda n:h((it['q']+'|'+n['node_id']).encode()))[:8]
    for n in nodes:
        spans=tok(n['text'],add_special_tokens=False,return_offsets_mapping=True,truncation=False,verbose=False)['offset_mapping']
        if not spans:continue
        # One source-contiguous query-blind selection for qualification, first 96 local model tokens.
        a=spans[0][0];b=spans[min(len(spans),96)-1][1]
        pairs.append([it['q'],it['t'],n['node_id'],h(n['text'][a:b].encode()),a,b,query,n['text'][a:b]])
assert len(pairs)>=32
t=time.perf_counter();ans=[]
with torch.inference_mode():
    for i in range(0,len(pairs),8):
        part=pairs[i:i+8];x=tok([v[-2] for v in part],[v[-1] for v in part],padding=True,truncation=False,return_tensors='pt');assert x['input_ids'].shape[1]<=512
        y=m(**x).logits[:,0].cpu();assert torch.isfinite(y).all()
        ans.extend([[*v[:6],float(z)] for v,z in zip(part,y,strict=True)])
elapsed=time.perf_counter()-t
out={'weights':h((p/'model.safetensors').read_bytes()),'queries':len(ids),'spans':len(ans),'forward_and_tokenize_seconds':elapsed,'torch':torch.__version__,'device':'cpu','threads':2,'batch':8,'max_passage_tokens':96,'rows':ans,'read_gold':False}
(Path(__file__).parent/'r23-minilm-smoke.json').write_text(json.dumps(out))
print(len(ids),len(ans),elapsed)

