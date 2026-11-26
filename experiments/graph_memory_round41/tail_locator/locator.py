"""Range-limited end-of-file witness and a full-file line-sequence comparator."""
from hashlib import sha256
import os

PAGE=4096

class Access:
    def __init__(self,handle):
        self.handle=handle;self.size=os.fstat(handle.fileno()).st_size;self.byte_count=0;self.calls=0
    def segment(self,start,count):
        self.handle.seek(start);data=self.handle.read(count);self.calls+=1;self.byte_count+=len(data);return data

def fields(raw,offset,at_begin):
    result=[];pos=0;items=raw.split(b'\n')
    for i,line in enumerate(items):
        finished=i<len(items)-1;visible=line[:-1] if finished and line.endswith(b'\r') else line
        if at_begin or i:
            result.append(((len(visible),sha256(visible).hexdigest()),offset+pos,offset+pos+len(visible)))
        pos+=len(line)+int(finished)
    return result

def candidate(rows,start,n):
    return (rows[start][1],rows[start+n-1][2])

def probe(store,token,form):
    if not token or form!='eof':return None,'unsupported_request'
    limit=min(store.size,sum(a[0] for a in token)+2*len(token)+4);begin=store.size-limit
    data=b''.join(store.segment(pos,min(PAGE,store.size-pos)) for pos in range(begin,store.size,PAGE))
    rows=fields(data,begin,begin==0);ends=[len(rows)]
    if data.endswith(b'\n'):ends.append(len(rows)-1)
    points={}
    for end in ends:
        start=end-len(token)
        if start>=0 and [r[0] for r in rows[start:end]]==token:
            pair=candidate(rows,start,len(token))
            points[pair]=sha256(data[pair[0]-begin:pair[1]-begin]).hexdigest()
    if len(points)!=1:return None,('ambiguous_endpoint' if points else 'suffix_mismatch')
    pos,raw_hash=next(iter(points.items()));return (pos[0],pos[1],raw_hash),'verified_at_receipt'

def full_scan(store,token):
    raw=store.segment(0,store.size);rows=fields(raw,0,True);n=len(token);out=[]
    # KMP over (length,SHA-256) per decoded display line. Avoid quadratic repeated-prefix matching.
    fail=[0]*n;j=0
    for i in range(1,n):
        while j and token[i]!=token[j]:j=fail[j-1]
        if token[i]==token[j]:j+=1
        fail[i]=j
    j=0
    for i,(key,_,_) in enumerate(rows):
        while j and key!=token[j]:j=fail[j-1]
        if key==token[j]:j+=1
        if j==n:
            lo=i-n+1;start,end=candidate(rows,lo,n)
            out.append((start,end,sha256(raw[start:end]).hexdigest(),lo+1,i+1));j=fail[j-1]
    return out,len(rows),raw.endswith(b'\n')

def selftest():
    from tempfile import TemporaryFile
    def run(raw,display,mode,expected,occurrences):
        tokens=[(len(s.encode()),sha256(s.encode()).hexdigest()) for s in display]
        with TemporaryFile() as h:
            h.write(raw);h.flush();local=Access(h);ans,status=probe(local,tokens,mode);entire=Access(h);all_spans,_,_=full_scan(entire,tokens)
            assert len(all_spans)==occurrences and entire.byte_count==len(raw)
            if expected is None:assert ans is None,(raw,ans)
            else:assert ans[:2]==expected and ans in [row[:3] for row in all_spans]
            assert local.byte_count<=min(len(raw),sum(z[0] for z in tokens)+2*len(tokens)+4)
            return {'probe':status,'bytes':local.byte_count,'full':entire.byte_count,'placements':len(all_spans)}
    return [run(b'head\nv\nx\nv\nx\n',['v','x'],'eof',(9,12),2),
            run('é\r\n雪\r\n'.encode(),['雪'],'eof',(4,7),1),
            run('é\r\n雪\r\n'.encode(),['雪',''],'eof',(4,9),1),
            run('字\né'.encode(),['é'],'eof',(4,6),1),
            run(b'v\n\n',[''],'eof',None,2),run(b'one\nx\n',['one'],'finite',None,1),
            run(b'other\n',['x'],'eof',None,0),run(b'head\r',['head\r'],'eof',(0,5),1),
            run(b'x'*15000+b'\na\nb\n',['a','b'],'eof',(15001,15004),1),
            run(b'past\nnow\n',['now'],'unknown',None,1),
            run(b'A\n'+b'X'*5500,[('X'*5500)],'eof',(2,5502),1)]
if __name__=='__main__':print(selftest())
