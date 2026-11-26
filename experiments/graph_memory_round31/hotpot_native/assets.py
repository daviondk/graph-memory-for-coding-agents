"""Verify or acquire pinned public assets for the Beam Retrieval replication."""
import argparse
import subprocess
from run import UP,WEIGHTS,HERE,sha,read

REPO="https://raw.githubusercontent.com/canghongjian/beam_retriever/902980bfb5bd47a963569ab9c3621fd5ae81204a/"
BACKBONE="https://huggingface.co/microsoft/deberta-v3-large/resolve/64a8c8eab3e352a784c658aef62be1662607476f/"

def ensure(target,url,digest):
    if target.exists():
        assert sha(target)==digest,target
        return
    target.parent.mkdir(parents=True,exist_ok=True)
    tmp=target.with_suffix(target.suffix+".part")
    subprocess.run(["curl","--fail","--silent","--show-error","--location","--retry","2","--max-time","900",url,"-o",str(tmp)],check=True)
    assert sha(tmp)==digest,(target,"digest mismatch")
    tmp.replace(target)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--weight-url",default="https://drive.usercontent.google.com/download?id=1LkPpjGUJkTwotGL0Luomy9IfU_S63UJ8&export=download&confirm=t")
    args=p.parse_args();plan=read(HERE/"plan.json")
    for name,digest in plan["author_code"].items():
        prefix={"retriever_model.py":"retrieval/","datasets.py":"retrieval/","config.py":"retrieval/","hotpot_pred_best_retr.json":"results/retrieval/"}.get(name,"")
        ensure(UP/name,REPO+prefix+name,digest)
    for name,digest in plan["tokenizer"].items():ensure(WEIGHTS/name,BACKBONE+name,digest)
    ensure(WEIGHTS/"hotpot_beam2_retr.pt",args.weight_url,plan["model_sha"])
    print("Verified source, tokenizer and model")
if __name__=="__main__":main()
