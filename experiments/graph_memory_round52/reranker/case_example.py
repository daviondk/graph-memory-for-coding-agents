"""Export the first stable-ID case with complete support gained and unchanged answer F1."""
from common import *
from reader import archive
def main():
    p="hotpot";records=get("records.json.gz")[p];a,b="ce_graph","ce_hybrid"
    keep=sorted(q for q,r in records.items() if r[a]["full"]>r[b]["full"] and r[a]["f1"]==r[b]["f1"])
    q=keep[0];src,cache=PANELS[p];question,docs=read(cache/"visible.json.gz")[q];titles={i:t for i,t,_ in docs}
    _,snippet,_=read(cache/"catalog-input.json.gz")[q];c=get("contexts.json.gz")[p][q]
    outs=archive()|get("new-answers.json.gz");g=read(src/"gold.json.gz")[q];arms={}
    for name in (a,b):
        i,k,n=c["refs"][name];arms[name]=dict(title=titles[i],index=i,hash=k,tokens=n,answer=outs[k]["answer"],**records[q][name])
    blob=dict(panel=p,id=q,selection="first qid sorted among full-support wins with identical answer F1",eligible=len(keep),
              question=question,first=titles[c["seed"]],first_index=c["seed"],first_snippet_already_contains_gold=g["answer"].lower() in snippet.lower(),
              gold_answer=g["answer"],gold_titles=[titles[i] for i,raw in enumerate(g["titles"]) if raw in g["support_titles"]],
              second_token_cap=c["cap"],arms=arms)
    put("case.json",blob)
if __name__=="__main__":main()
