"""Frozen gates on ranked IDs; compare detached metadata without reading relevance labels."""
from common import HERE, load, save, sha

def decide(r):
    ranks=r["ranks"]
    leader=ranks["fusion"][0]
    skip_two=leader==ranks["sparse_fields"][0]
    skip_three=skip_two and leader==ranks["bm25_outcome"][0]
    scores={k:(v[0],0,0) for k,v in ranks.items()}
    readers={**r["readers"],"mini_reader":(ranks["minilm"][0],0,0)}
    for k, full in readers.items():
        scores[k]=full
        if k=="recall_five":continue
        assert full[0] in ranks["fusion"][:5]
        scores[k+"_three"]=(leader,0,0) if skip_three else full
        scores[k+"_two"]=(leader,0,0) if skip_two else full
    return {"skip_three":skip_three,"skip_two":skip_two,"scores":scores}

def main():
    inp=load(HERE/"inputs.json.gz")
    save("decisions.json.gz",[decide(r) for r in inp])
    save("decision-seal.json",{n:sha(HERE/n) for n in ("decide.py","PROTOCOL.md","inputs.json.gz","decisions.json.gz","source.json")})

if __name__=="__main__":main()

