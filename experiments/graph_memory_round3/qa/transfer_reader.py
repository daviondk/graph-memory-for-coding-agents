"""Fixed alternatives for rendering source-attributed evidence. No answer is used for prediction."""
import calendar,datetime as dt,re,json,gzip,time
import numpy as np
from emb import fields,session,batch,rewrite,OTHER
from prepare import P,read,write,sha
DAYS={x.lower():j for j,x in enumerate(calendar.day_name)}
WORDS=dict(one=1,two=2,three=3,four=4,five=5,six=6,seven=7)
PAT=re.compile(r"\b(yesterday|today|tomorrow|last night|this (?:morning|afternoon|evening|year|month)|last (?:year|month|weekend|week|monday|tuesday|wednesday|thursday|friday|saturday|sunday)|(?:[1-9]|one|two|three|four|five|six|seven) (?:day|week)s? ago)\b",re.I)
def date(s):
    return dt.datetime.strptime(s.split(" on ")[-1].replace(",",""),"%d %B %Y").date()
def fmt(d):return f"{d.day} {d.strftime('%B %Y')}"
def grounded(text,day):
    def stamp(m):
        label=m[0].lower();word=label.split()[-1];prior=day-dt.timedelta(days=1)
        mon=day-dt.timedelta(days=day.weekday());val=None
        if word in DAYS:
            val=fmt(day-dt.timedelta(days=(day.weekday()-DAYS[word])%7 or 7))
        elif label in ("last year","this year"):val=str(day.year-int(label=="last year"))
        elif label in ("last month","this month"):
            month=(day.replace(day=1)-dt.timedelta(days=1)) if label=="last month" else day;val=month.strftime("%B %Y")
        elif label in ("last weekend","last week"):
            first=mon-dt.timedelta(days=2 if label=="last weekend" else 7);end=mon-dt.timedelta(days=1)
            val=fmt(first)+" to "+fmt(end)
        elif word=="ago":
            n=label.split()[0];n=int(n) if n.isdigit() else WORDS[n];n*=7 if 'week' in label else 1
            val=fmt(day-dt.timedelta(days=n))
        else:
            shift=1 if label=="tomorrow" else (-1 if label in ("yesterday","last night") else 0);val=fmt(day+dt.timedelta(days=shift))
        return m[0]+" ["+val+"]"
    return PAT.sub(stamp,text)
def main():
    start=time.time();g=read("gold.json");pilot=set(read("reader_lock.json")["questions"]);data=read("input.json")
    ranks=json.loads(gzip.decompress((P/'predictions.json.gz').read_bytes()));ids=[];mapping={};pool={};metadata={}
    arms=['flat','graph','owner','date','joint','wrong_date','previous','directed']
    for c in data:
        turns=c['turns'];index={t['id']:j for j,t in enumerate(turns)};people=sorted({t['speaker'] for t in turns})
        dates=list(dict.fromkeys(t['time'] for t in turns));successor=dict(zip(dates,dates[1:]+dates[:1]))
        prev=[j-1 if j>0 and turns[j-1]['session']==t['session'] and turns[j-1]['speaker']!=t['speaker'] else None for j,t in enumerate(turns)]
        nxt=[j+1 if j+1<len(turns) and turns[j+1]['session']==t['session'] and turns[j+1]['speaker']!=t['speaker'] else None for j,t in enumerate(turns)]
        cache={}
        for j,t in enumerate(turns):
            speaker=t['speaker'];other=next(p for p in people if p!=speaker);l=prev[j];r=nxt[j]
            for a in arms:
                text=t['text'];label=''
                if a in ('owner','joint','wrong_date'):text=rewrite(text,speaker,other)
                if a in ('date','joint','wrong_date'):text=grounded(text,date(successor[t['time']] if a=='wrong_date' else t['time']))
                if a in ('previous','directed'):
                    neighbor=l
                    if a=='directed':
                        neighbor=l if l is not None and '?' in turns[l]['text'] else (r if r is not None and OTHER.search(turns[r]['text']) else None)
                    if neighbor is not None:label=" [Context: "+turns[neighbor]['speaker']+" "+" ".join(turns[neighbor]['text'].split()[:8])+"]"
                cache[a,j]=str(t['time'])+" | "+speaker+": "+text+(" (Image: "+t['caption']+")" if t['caption'] else '')+label
        for q in c['queries']:
            key=q['id'];ann=g[key]
            if key in pilot or ann['cat'] not in (1,2,3,4) or not ann['evidence'] or not set(ann['evidence'])<=index.keys():continue
            ids.append(key);mapping[key]={}
            for a in arms:
                ix=[index[t] for t in ranks[key]['flat' if a=='flat' else 'graph'][0][:5]]
                ctx="\n".join(cache[a,j] for j in ix);k=sha(q['text']+"\n"+ctx)
                pool[k]=(q['text'],ctx);mapping[key][a]=k
            metadata[key]={"explicit_relative_date_in_top5":any(PAT.search(turns[j]['text']) for j in ix)}
    write('transfer_lock.json',dict(method_sha=sha((P/'transfer_reader.py').read_bytes()),protocol_sha=sha((P/'READER_TRANSFER.md').read_bytes()),upstream_predictions=sha((P/'predictions.json.gz').read_bytes()),n=len(ids),excluded_pilot=len(pilot),items=ids,arms=arms))
    write('transfer_features.json',metadata)
    so,tok=session('reader');out={};order=sorted(pool,key=lambda k:(len(pool[k][1]),k))
    for lo in range(0,len(order),8):
        bucket=order[lo:lo+8];enc=tok.encode_batch([pool[key] for key in bucket]);(st,en),mask=batch(so,enc)
        for j,(k,v) in enumerate(zip(bucket,enc)):
            eligible=np.array([s==1 for s in v.sequence_ids]);best=-1e12;S=E=None
            for width in range(1,25):
                score=st[j,:len(eligible)-width+1]+en[j,width-1:];ok=eligible[:len(score)]&eligible[width-1:]
                vi=np.where(ok,score,-1e20);l=int(np.argmax(vi))
                if vi[l]>best:best=float(vi[l]);S=l;E=l+width-1
            assert S is not None
            out[k]=dict(answer=pool[k][1][v.offsets[S][0]:v.offsets[E][1]],tokens=int(mask[j].sum()),truncated=bool(v.overflowing))
        if lo%1600==0:print(f'{lo}/{len(order)}',flush=True)
    write("transfer_output.json",{i:{a:out[k] for a,k in m.items()} for i,m in mapping.items()})
    write("transfer_receipt.json",dict(seconds=time.time()-start,n=len(ids),unique_forward_examples=len(out),logical=len(ids)*len(arms),sha256=sha((P/'transfer_output.json').read_bytes()),tokens=sum(x['tokens'] for x in out.values())))
if __name__=='__main__':main()