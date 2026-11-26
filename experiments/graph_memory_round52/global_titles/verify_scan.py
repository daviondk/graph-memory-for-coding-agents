"""Independent, brute-force check of every policy on a deterministic label-free sample."""
from collections import Counter, defaultdict
from hashlib import sha256
import math
import struct
from corpus import ROOT, WORK, read, save, hashfile
from seal import ARMS

def enumerate_titles():
    buf=(WORK/"lex.bin").read_bytes()
    lo=0;row=0
    while lo<len(buf):
        page,n,usable=struct.unpack_from("<IHH",buf,lo);lo+=8
        seq=struct.unpack_from(f"<{n}I",buf,lo);lo+=4*n
        yield row,page,seq,usable
        row+=1
    assert row==5989847

def inside(s,t):
    return len(s)>0 and any(t[i:i+len(s)]==s for i in range(len(t)) if t[i]==s[0])

def main():
    seal=read(ROOT/"prediction-seal.json")
    assert all(hashfile(ROOT/k)==v for k,v in seal["files"].items())
    selected=read(ROOT/"predictions.json.gz")
    ids=sorted(selected,key=lambda q:sha256(("independent-directory-scan|"+q).encode()).digest())[:8]
    queries={};prefix={};links={}
    for line in (WORK/"questions.in").read_text().splitlines():
        q,*x=line.split()
        if q in ids:queries[q]=tuple(map(int,x))
    for line in (WORK/"second.in").read_text().splitlines():
        q,seed,n,*xs=line.split()
        if q in ids:
            assert int(seed)==selected[q][0]
            x=list(map(int,xs));links[q]=set(x[:int(n)]);prefix[q]=tuple(x[int(n):])
    stop=(WORK/"stop.bin").read_bytes()
    vocab={w for q in ids for w in (*queries[q],*prefix[q]) if not stop[w]}
    df=Counter();length=0;nrow=0
    for row,page,seq,usable in enumerate_titles():
        ts=[w for w in seq if not stop[w]];length+=len(ts);nrow+=1
        df.update(vocab.intersection(ts))
    avg=length/nrow;idf={w:math.log1p((nrow-v+.5)/(v+.5)) for w,v in df.items()}
    wp=defaultdict(set);referenced=defaultdict(set)
    for q in ids:
        for w in (*queries[q],*prefix[q]):
            if not stop[w]:wp[w].add(q)
        for row in links[q]:referenced[row].add(q)
    first={q:[] for q in ids};second={q:[] for q in ids}
    for row,page,seq,usable in enumerate_titles():
        candidates=set(referenced.get(row,()))
        for w in seq:candidates.update(wp.get(w,()))
        if not candidates:continue
        tf=Counter(w for w in seq if not stop[w]);norm=1.2*(.25+.75*sum(tf.values())/avg)
        words=sorted(set(tf)&vocab)
        for q in candidates:
            qw=set(queries[q]);pw=set(prefix[q]);explicit=bool(usable and inside(seq,queries[q]))
            literal=bool(usable and inside(seq,prefix[q]));href=row in links[q]
            raw=sum(idf[w]*(2.2*tf[w]/(tf[w]+norm)) for w in words if w in qw)
            joint=sum((idf[w]*((w in qw)+.25*(w in pw)))*(2.2*tf[w]/(tf[w]+norm)) for w in words)
            if raw or explicit:first[q].append((explicit,raw,-page,-row))
            if row!=selected[q][0]:
                second[q].append((explicit,joint,-page,-row,raw,literal,href))
    for q in ids:
        seed,plain,choices,counts,*_=selected[q]
        winners=first[q]; assert -max(winners)[3]==seed
        assert -max(winners,key=lambda r:r[1:])[3]==plain
        r=second[q];base=max(r,key=lambda d:d[:4]);raw=max(r,key=lambda d:(d[4],d[2],d[3]))
        e=[d for d in r if d[0]];ll=[d for d in r if d[5]];hh=[d for d in r if d[6]]
        assert counts==[len(e),len(ll),len(hh),sum(d[5] and d[6] for d in r)]
        def by_edge(flag,direct):
            pool=[d for d in r if flag(d) and (not direct or not e or d[0])]
            return max(pool,key=lambda d:d[:4] if direct else d[1:4]) if pool else base
        got=[base,raw,by_edge(lambda d:d[5],True),by_edge(lambda d:d[6],True),
             by_edge(lambda d:d[5] or d[6],True),by_edge(lambda d:d[5],False),by_edge(lambda d:d[6],False)]
        assert choices==[-d[3] for d in got],q
    save(ROOT/"brute-force.json",dict(n_questions=len(ids),n_records=nrow,selections=len(ids)*(2+len(ARMS)),
        verified_ids=ids,method="Independent complete two-pass directory scan; exact phrase, score and tie order.",seal=hashfile(ROOT/"prediction-seal.json")))
    print("Verified",len(ids),"questions from",nrow,"titles",flush=True)
if __name__=="__main__":main()

