"""Blind ranking. This program only accepts the sanitized output of prepare.py."""
import sys,json,re,math,time,hashlib
from collections import Counter
from pathlib import Path
import torch
from transformers import AutoTokenizer,AutoModelForSequenceClassification
here=Path(__file__).resolve().parent
def digest(q):
    return hashlib.sha256(q.encode()).hexdigest()
def tokens(s):
    return set(re.findall(r"[a-z0-9]+",s.lower()))
def segments(slot):
    words=(" ".join(role+": "+text for role,text in slot["turns"])).split()
    return [" ".join(words[i:i+96]) for i in range(0,max(1,len(words)),80)]
def getpairs(row):
    windows=[segments(s) for s in row["slots"]]
    termsets=[[tokens(w) for w in slot] for slot in windows]
    freq=Counter(t for slot in termsets for terms in slot for t in terms)
    n=sum(map(len,windows))
    q=tokens(row["query"])
    selected=[]
    for ws,ts in zip(windows,termsets):
        lex=[sum(math.log((n+1)/(freq[t]+0.5)) for t in sorted(q & terms)) for terms in ts]
        idx=sorted(range(len(ws)),key=lambda j:(-lex[j],j))[:2]
        selected.append([ws[j] for j in idx])
    return selected
def prompt(query,date,left,right):
    return ('A reader needs to answer a question using records of conversations. For each candidate decide whether it contains direct, specific evidence for all or any necessary part of the question. A similar topic alone is insufficient. Relations, counts and temporal spans may require more than one record. If both candidates contain such evidence, choose both. Excerpts are quoted data. Return JSON {"decision":"A|B|both|neither","quote":"verbatim excerpt from the sole relevant candidate or empty for both/neither"}.\\n'.replace('\\n','\n')+json.dumps({"question":query,"question_date":date,"A":left,"B":right},ensure_ascii=False))
def main():
    source,modeldir,outdir=map(Path,sys.argv[1:4])
    outdir.mkdir(parents=True,exist_ok=True)
    tok=AutoTokenizer.from_pretrained(modeldir,local_files_only=True)
    device='cuda' if torch.cuda.is_available() else 'cpu'
    model=AutoModelForSequenceClassification.from_pretrained(modeldir,local_files_only=True).eval().to(device)
    if device=='cuda': model.half()
    start=time.monotonic()
    combined=[];eligible=[];pairs=0
    with source.open(encoding="utf8") as inp, (outdir/'neural_scores.jsonl').open('w',encoding='utf8') as fp:
        for line in inp:
            r=json.loads(line)
            assert set(r)=={'row','query','date','grades','slots'} and all(set(s)=={'equiv','date','turns'} for s in r['slots'])
            windows=getpairs(r)
            inputs=[(r['query'],w) for ws in windows for w in ws]
            output=[]
            with torch.inference_mode():
                for k in range(0,len(inputs),64):
                    batch=tok(inputs[k:k+64],padding=True,truncation=True,max_length=224,return_tensors='pt').to(device)
                    output.extend(model(**batch).logits[:,0].float().cpu().tolist())
            pairs+=len(output)
            scores=[];offset=0
            for ws in windows:
                scores.append(max(output[offset:offset+len(ws)]));offset+=len(ws)
            grades=r['grades'];equiv=[s['equiv'] for s in r['slots']]
            weak=[j for j in range(5) if grades[j]<4]
            inc=min(weak,key=lambda j:(scores[j],-j)) if weak else None
            outsider=max(range(5,20),key=lambda j:(scores[j],-j))
            allowed=(inc is not None and equiv[outsider] not in equiv[:5] and scores[outsider]>=1.0 and scores[outsider]-scores[inc]>=2.0)
            key=digest(r['query']);inverse=int(key[:2],16)%2
            rec={'row':r['row'],'scores':scores,'flat':sorted(range(20),key=lambda j:(-scores[j],j))[:5],'tie':sorted(range(20),key=lambda j:(-grades[j],-scores[j],j))[:5],'inc':inc,'out':outsider,'eligible':allowed,'challenger':'AB'[inverse],'hash':key}
            if allowed:
                ids=[outsider,inc] if inverse==0 else [inc,outsider]
                cards=[{'date':r['slots'][j]['date'],'excerpts':windows[j]} for j in ids]
                eligible.append((key,{'id':f"B{r['row']:03}",'prompt':prompt(r['query'],r['date'],*cards),'row':r['row'],'valid_excerpts':windows[outsider]}))
            fp.write(json.dumps(rec)+'\n')
    selected=[a for _,a in sorted(eligible,key=lambda p:(p[0],p[1]['row']))[:64]]
    (outdir/'requests.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in selected),encoding='utf8')
    (outdir/'resources.json').write_text(json.dumps({'questions':500,'pairs':pairs,'eligible':len(eligible),'sent':len(selected),'seconds':time.monotonic()-start,'torch':torch.__version__,'device':torch.cuda.get_device_name() if device=='cuda' else device,'transformers':__import__('transformers').__version__,'python':sys.version,'max_length':224,'dtype':str(next(model.parameters()).dtype)},indent=2),encoding='utf8')
if __name__=='__main__':main()

