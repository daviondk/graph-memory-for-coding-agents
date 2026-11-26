"""Portable audit of stored witnesses, the two-read choice and every support/CI aggregate."""
from common import *
from grade import calculate
def close(a,b):
    if isinstance(a,dict):return a.keys()==b.keys() and all(close(a[k],b[k]) for k in a)
    if isinstance(a,list):return len(a)==len(b) and all(close(x,y) for x,y in zip(a,b))
    if isinstance(a,float):return abs(a-b)<1e-10
    return a==b
def main():
    manifest=read(D/"manifest.json")["files"];assert all(sha(D/n)==v for n,v in manifest.items())
    pri=read(D/"prediction_seal.json");cl=read(D/"clip-seal.json");met=read(D/"results.json");extra=read(D/"clip-results.json")
    assert pri["protocol"]==sha(D/"PROTOCOL_RU.md") and pri["source"]==sha(D/"source.json")
    for split in CONFIG:
        pp=D/f"forecast-{split}.json.gz";cp=D/f"clip-{split}.json.gz"
        assert pri["subsets"][split]["predictions"]==sha(pp) and cl["predictions"][split]==sha(cp)
        pred=read(pp);clipped=read(cp);truth=read(D/f"support-{split}.json.gz")
        assert set(pred)==set(clipped)==set(truth)
        for q,r in pred.items():
            order=r["sort"];truth_titles,_=truth[q];seed=r["seed"]
            assert sorted(order+[seed])==list(range(len(truth_titles)))
            text,href,direct=map(set,(r["text_edges"],r["href_edges"],r["direct_edges"]))
            assert not ({seed}&(text|href|direct))
            choose=lambda s:next((i for i in order if i in s),order[0])
            variants={"lex":order[0],"text":choose(text),"href":choose(href),"direct":choose(direct),"union":choose(text|href),"literal":choose(href) if r["prefix_literal"] else order[0]}
            assert variants==r["choices"]
            assert {w[0] for w in r["witness"]}==href
            for k,j,a,b,stop,end,anchor,uri,ref_ids,in_name,in_id in r["witness"]:
                assert 0<=j and 0<=a<b and stop<=end and len(anchor)==len(uri)==64 and (in_name or in_id)
            if r["status"]!="ok":assert not href and not r["witness"]
            ok,edges,choice=clipped[q];assert choose(set(edges))==choice
        hand=read(D/"handoff.json")["subsets"][split]
        hp=D/hand["file"];assert sha(hp)==hand["sha256"]
        deployed=read(hp);assert set(deployed)==set(pred)
        for q,item in deployed.items():
            row=pred[q];ok,edges,second=clipped[q]
            joint=set(edges)|set(row["text_edges"])
            combined=next((i for i in row["sort"] if i in joint),row["sort"][0])
            assert item=={"seed":row["seed"],"href":second,"union":combined,"text":row["choices"]["text"],"lex":row["choices"]["lex"]}
        got=calculate(pred,truth)
        assert close(got,{k:v for k,v in met[split].items() if k!="source_gold_sha"})
        n=sum(clipped[q][2]!=r["choices"]["href"] for q,r in pred.items())
        for q,row in pred.items():row["choices"]["href"]=clipped[q][2]
        alt=calculate(pred,truth)
        assert extra[split]["changed"]==n and extra[split]["href_complete"]==alt["complete"][2]
        assert close(extra[split]["against_text"],alt["contrasts"]["href-text"])
    print("Verified 1,600 queries, six frozen choices per query, paired cluster bootstraps and visibility-only sensitivity.")
if __name__=="__main__":main()

