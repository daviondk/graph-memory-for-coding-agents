"""CPU capacity measured on prespecified SHA-sorted examples among missing full-length passages."""
import sys,time,torch,numpy as np
from setup_graph import ROOT,TR,RUN,TRAINED,load,put,pilot
from vectors import database
from graph_memory.embeddings import load_sentence_transformer
def run():
    c=database();ss=c.execute("select txt from corpus s where base=1 and n>1800 and not exists(select 1 from vectors v where v.k=s.k and v.prec='base') order by k limit 16").fetchall();ss=[s for s, in ss]
    torch.set_num_threads(8);model=load_sentence_transformer(str(TRAINED/'model'),device='cpu').eval()
    notes={}
    for mode in ['bf16','fp32']:
        with torch.inference_mode():
            reps=[]
            for n in (2,8):
                start=time.monotonic()
                with torch.autocast('cpu',dtype=torch.bfloat16,enabled=(mode=='bf16')):
                    f=model.tokenize(ss[:n]);y=model.forward(f)['sentence_embedding']
                    proj=torch.nn.functional.normalize(y.float(),dim=1).cpu().numpy()
                reps.append(dict(n=n,seconds=time.monotonic()-start))
        notes[mode]=reps;print(mode,reps,flush=True)
    put(ROOT/'cpu-bench.json',dict(threads=8,torch=torch.__version__,device='AMD Ryzen 7 8700F',times=notes,input_lengths=[len(s) for s in ss[:8]],note='Diagnostic only, not a replacement encoder or evaluation.'))
if __name__=='__main__':run()

