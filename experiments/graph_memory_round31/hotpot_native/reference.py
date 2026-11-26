"""Compute official released retrieval quality on the full dev corpus without reranking."""
import gzip
import json
from collections import Counter
from run import HERE,UP,BLIND,sha,read,put


def main():
    plan=read(HERE/"plan.json")
    path=UP/"hotpot_pred_best_retr.json"
    assert sha(path)==plan["author_code"][path.name] and sha(BLIND)==plan["blind"]
    source=read(HERE.parent/"support_pairs/source.json")
    labels_path=BLIND.with_name("labels.json.gz")
    assert sha(labels_path)==source["labels"]
    with gzip.open(BLIND,"rt",encoding="utf8") as stream: data=json.load(stream)
    with gzip.open(labels_path,"rt",encoding="utf8") as stream: labels=json.load(stream)
    published=read(path)
    assert set(published)==set(labels)==set(data)
    groups={}
    for q,ids in published.items():
        titles=data[q]["titles"]
        assert len(ids)==2 and len(set(ids))==2 and all(0<=i<len(titles) for i in ids)
        refs=set(labels[q]["support"])
        assert len(refs)==2
        hits=len({titles[i] for i in ids}&refs)
        for group in ("all",labels[q]["type"]):
            groups.setdefault(group,Counter()).update(questions=1,both=int(hits==2),hits=hits)
    put(HERE/"official-reference.json",{"prediction_sha":sha(path),"labels_sha":sha(labels_path),"source_sha":sha(BLIND),"by_group":groups,
                                      "method":"author released passage pairs, without withdrawals","evaluation_code":sha(HERE/"reference.py")})
    print(groups)
if __name__=="__main__":main()
