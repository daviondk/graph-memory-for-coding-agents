"""Report one measured CPU startup with third-party imports and locally cached files."""
import time
start=time.perf_counter()
from run import HERE,sha,put,load_model
import psutil,torch
from transformers import AutoTokenizer
imports=time.perf_counter()
torch.set_num_threads(2)
torch.set_num_interop_threads(1)
proc=psutil.Process()
if hasattr(psutil,"BELOW_NORMAL_PRIORITY_CLASS"):proc.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
t=time.perf_counter()
model,tok,_=load_model()
loaded=time.perf_counter()
put(HERE/"initial-cost.json",{"imports_seconds":imports-start,"model_and_tokenizer_seconds":loaded-t,
    "end_to_end_seconds":loaded-start,"working_set_bytes":proc.memory_info().rss,
    "peak_working_set_bytes":getattr(proc.memory_info(),"peak_wset",proc.memory_info().rss),
    "model_parameters":sum(p.numel() for p in model.parameters()),"model_dtype":str(next(model.parameters()).dtype),
    "procedure":"1 repetition, mmap local checkpoint, OS cache uncontrolled, no forward","code":sha(HERE/"initial_cost.py")})
