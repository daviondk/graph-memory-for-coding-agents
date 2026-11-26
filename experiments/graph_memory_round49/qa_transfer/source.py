"""Fetch the official archive as data, audit its two answerable split members and project visible fields."""
import json
import shutil
import zipfile
from collections import Counter
import requests
from common import *
from panel import norm

def dh(p):return hexb((p["title"]+"\0"+p["paragraph_text"]).encode())
def main():
    check();P.mkdir(exist_ok=True)
    raw=P/"musique_v1.0.zip"
    if not raw.exists():
        tmp=P/"official-downloading.zip"
        with requests.get(URL,stream=True,timeout=(15,180)) as response, tmp.open("wb") as out:
            response.raise_for_status()
            for part in response.iter_content(1<<20):out.write(part)
        with zipfile.ZipFile(tmp) as z:assert z.getinfo("data/musique_ans_v1.0_dev.jsonl").file_size>0
        tmp.replace(raw)
    panel=set(get(R46/'panel.json')['order'])
    pools={k:{'ids':set(),'questions':set(),'docs':set()} for k in ('full_train','r46_train_panel')}
    dev_forms={};view={};docsets={};proof={}
    with zipfile.ZipFile(raw) as z:
        for stage,mirror in [('dev',DEV),('train',TRAIN)]:
            path='data/musique_ans_v1.0_'+stage+'.jsonl';target=P/('official-'+stage+'.jsonl')
            with z.open(path) as inp,target.open('wb') as out:shutil.copyfileobj(inp,out)
            same=sha(target)==sha(mirror);lines=0;consistent=True
            with target.open(encoding='utf8') as off,mirror.open(encoding='utf8') as backup:
                for a,b in zip(off,backup,strict=True):
                    r=json.loads(a);lines+=1
                    if not same:assert r==json.loads(b)
                    q=r['id'];question=norm(r['question']);docs={dh(x) for x in r['paragraphs']}
                    if stage=='dev':
                        assert q not in view
                        view[q]=[r['question'],[[x['idx'],x['title'],x['paragraph_text']] for x in r['paragraphs']]]
                        dev_forms[q]=question;docsets[q]=docs
                    else:
                        for key in ('full_train','r46_train_panel') if q in panel else ('full_train',):
                            pool=pools[key];pool['ids'].add(q);pool['questions'].add(question);pool['docs'].update(docs)
            proof[stage]=dict(member=path,official_sha256=sha(target),mirror_sha256=sha(mirror),identical_bytes=same,
                              json_rows_equal=True,lines=lines)
    assert len(view)==2417 and len(pools['r46_train_panel']['ids'])==1024
    dd=set.union(*docsets.values());over={};seen={}
    for key,pool in pools.items():
        overlap=dd&pool['docs'];seen[key]=sorted(overlap)
        over[key]=dict(source_ids=len(pool['ids']),source_questions=len(pool['questions']),source_docs=len(pool['docs']),
                       dev_questions_reusing_id=len(set(view)&pool['ids']),dev_questions_reusing_question=sum(v in pool['questions'] for v in dev_forms.values()),
                       shared_distinct_documents=len(overlap),dev_questions_with_any_shared_doc=sum(bool(s&overlap) for s in docsets.values()))
    put(P/'visible.json.gz',view);put(P/'seen-documents.json.gz',seen)
    put(D/'source-seal.json',dict(archive=sha(raw),url=URL,splits=proof,overlap=over,dev_unique_docs=len(dd),
        dev_unique_forms=len(set(dev_forms.values())),visible=sha(P/'visible.json.gz'),seen=sha(P/'seen-documents.json.gz'),code=sha(Path(__file__))))
    print(proof,over,flush=True)

if __name__=='__main__':main()
