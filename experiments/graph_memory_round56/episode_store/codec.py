"""Self-contained codecs for exact incident events and byte-bounded anchor state."""
from collections import Counter
from struct import iter_unpack, pack

def uint(value):
    assert value >= 0
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)

def readuint(data, pos):
    value = shift = 0
    while True:
        byte = data[pos]
        pos += 1
        value |= (byte & 127) << shift
        if byte < 128:
            return value, pos
        shift += 7

def ids_blob(ids):
    data = bytearray()
    prev = -1
    for i in ids:
        assert i > prev
        data.extend(uint(i-prev))
        prev=i
    return bytes(data)

def blob_ids(data):
    ids = []
    pos = 0
    prev = -1
    while pos < len(data):
        step,pos=readuint(data,pos)
        assert step>0
        prev+=step
        ids.append(prev)
    return tuple(ids)

def unpack_events(data):
    """Records prefixed by positive vote count. Zero padding terminates the packet."""
    pos=0
    result=[]
    while pos<len(data) and data[pos]:
        count,pos=readuint(data,pos)
        size,pos=readuint(data,pos)
        result.append((count,data[pos:pos+size]))
        pos+=size
    return result

def record(count,members):
    assert count>0
    return uint(count)+uint(len(members))+members

def store_events(records,budget):
    out=bytearray()
    for count, members in records:
        rec=record(count,members)
        if len(out)+len(rec)>budget:
            break
        out.extend(rec)
    return bytes(out).ljust(budget,b'\0')

def counts_blob(scores):
    out=bytearray()
    prev=-1
    for i,n in sorted(scores.items()):
        out.extend(uint(i-prev))
        out.extend(uint(n))
        prev=i
    return bytes(out)

def blob_counts(data):
    out={}
    prev=-1
    pos=0
    while pos<len(data) and data[pos]:
        gap,pos=readuint(data,pos)
        n,pos=readuint(data,pos)
        prev+=gap
        out[prev]=n
    return out

def profile(mode,data):
    if mode=='space':
        return {i-1:n for i,n in iter_unpack('<HH',data) if i}
    if mode=='lossy':
        return blob_counts(data)
    out=Counter()
    for n, item in unpack_events(data):
        for i in blob_ids(item):
            out[i]+=n
    return out

def bounded_update(mode, previous, peers, budget):
    """Rows always have exactly budget bytes and no reference outside the row."""
    if mode=='space':
        scores=profile(mode,previous)
        for i in peers:
            if i in scores:
                scores[i]+=1
            elif len(scores)<budget//4:
                scores[i]=1
            else:
                least=min(scores,key=lambda k:(scores[k],-k))
                scores[i]=scores.pop(least)+1
        data=b''.join(pack('<HH',i+1,n) for i,n in sorted(scores.items()))
        return data.ljust(budget,b'\0')
    if mode=='lossy':
        scores=blob_counts(previous)
        for i in peers:
            scores[i]=scores.get(i,0)+1
            while len(counts_blob(scores))>budget:
                least=min(scores,key=lambda k:(scores[k],-k))
                del scores[least]
        return counts_blob(scores).ljust(budget,b'\0')
    if not peers and mode!='raw':
        return previous
    payload=ids_blob(peers)
    if len(record(1,payload))>budget:
        return previous
    records=unpack_events(previous)
    if mode=='runs' and records and records[0][1]==payload:
        count, old=records[0]
        # Should a long run alone exceed B after a count-width transition, cap its vote.
        records[0]=(count+1,old) if len(record(count+1,old))<=budget else (count,old)
    else:
        records.insert(0,(1,payload))
    return store_events(records,budget)
