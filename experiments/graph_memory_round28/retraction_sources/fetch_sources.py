from urllib.request import urlopen,Request
from shutil import copyfileobj
from formats import *
PUBLIC={
 "fact.parquet":"https://huggingface.co/datasets/ai-hyz/MemoryAgentBench/resolve/7ea066982b140a19337e17e60d45d4076e042faf/data/Conflict_Resolution-00000-of-00001.parquet",
 "halumem-medium.jsonl":"https://huggingface.co/datasets/IAAR-Shanghai/HaluMem/resolve/cb04336aa1b732d4b24f5186c552456b4099806e/HaluMem-Medium.jsonl",
 "stale.json":"https://huggingface.co/datasets/STALEproj/STALE/resolve/617c51dc200b5ab09970834144c7e51c77959af0/T1_T2_400_FULL.json",
}
ON_GITHUB={"run_target_model.py.txt":("icedreamc/STALE","ea7d391103a151927cd29d2f01d87597a782bdcb","STALE/Evaluation/run_target_model.py"),"judge_prompts.py.txt":("icedreamc/STALE","ea7d391103a151927cd29d2f01d87597a782bdcb","STALE/Evaluation/judge_prompts.py"),"evaluate_qa.py.txt":("xiaowu0162/LongMemEval","9e0b455f4ef0e2ab8f2e582289761153549043fc","src/evaluation/evaluate_qa.py")}
for name in ("ground_truth.jsonl","tasks_full_session.jsonl","clean/clean_memories.jsonl","faulty/stale/faulty_memories.jsonl"):
    ON_GITHUB["rollback-"+name.replace("/","-")]=("xiaoqi-7/memory-rollback","713724491b9bbc6e55f0f9d8723da0eb0766ced7","data/controlled_benchmark/customer_support/"+name)
def get(p,url):
    if p.exists():return
    p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+".part")
    with urlopen(Request(url,headers={"User-Agent":"Academic memory benchmark audit"}),timeout=90) as src,tmp.open("wb") as out:copyfileobj(src,out)
    tmp.replace(p)
if __name__=="__main__":
    for k,u in PUBLIC.items():get(P/k,u)
    for k,vals in ON_GITHUB.items():get(P/k,"https://raw.githubusercontent.com/"+"/".join(vals))
    get(LM,"https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/resolve/98d7416c24c778c2fee6e6f3006e7a073259d48f/longmemeval_s_cleaned.json")
    for p,h in PINS.items():assert sha(p)==h,p

