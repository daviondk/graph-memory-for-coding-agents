"""Independent visibility-only sensitivity: clip the annotation stream before validation."""
from common import *
from predict import inspect_source
def main():
    docs=read(PRIVATE/"sources.json.gz");ids=read(PRIVATE/"titles.json.gz")
    with_rows={}
    for split,study in CONFIG.items():
        old=read(D/f"forecast-{split}.json.gz");view=read(visible(split))
        new={}
        for q,r in old.items():
            catalog=view[q][1];seed=r["seed"];full=catalog[seed][2];snippet=full[:r["chars"]];assert textsha(snippet)==r["prefix_sha"]
            titles=[title(t) for _,t,_ in catalog];candidates0=docs.get(titles[seed],[])
            valid=[]
            for id0,sentences,mentions in candidates0:
                body=" ".join(sentences);chars=[i for i,k in enumerate(body) if not k.isspace()]
                n=len(compact(snippet))
                if n==0 or not compact(body).startswith(compact(snippet)):continue
                end=chars[n-1]+1;offsets=[];s=0
                for sent in sentences:offsets.append(s);s+=len(sent)+1
                visible_mentions=[]
                for m in mentions:
                    j=m.get("sent_idx");a=m.get("start")
                    if isinstance(j,int) and 0<=j<len(sentences):
                        if offsets[j]>=end or isinstance(a,int) and offsets[j]+a>=end:continue
                    visible_mentions.append(m)
                v=inspect_source([id0,sentences,visible_mentions],snippet,full,titles,ids,seed)
                if v is not None:valid.append(v)
            good=bool(valid) and not any(v.get("invalid") for v in valid) and len({(tuple(v["href"]),tuple(v["direct"])) for v in valid})==1
            links=valid[0]["href"] if good else []
            selected=next((i for i in r["sort"] if i in links),r["sort"][0])
            new[q]=[good,links,selected]
        f=D/f"clip-{split}.json.gz";write(f,new)
        print(split,"usability changes",sum(v[0]!=(old[q]["status"]=="ok") for q,v in new.items()),"ID changes",sum(v[2]!=old[q]["choices"]["href"] for q,v in new.items()))
        with_rows[split]=sha(f)
    write(D/"clip-seal.json",{"predictions":with_rows,"primary":sha(D/"prediction_seal.json"),"code":sha(Path(__file__))})
if __name__=="__main__":main()

