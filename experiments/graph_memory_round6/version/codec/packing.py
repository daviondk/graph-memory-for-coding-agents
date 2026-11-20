import sys
from pathlib import Path
from compression import zstd

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from version_policy import old
import schema_codec as lib


def varint(n,out):
    assert n>=0
    while n>=128:
        out.append((n&127)|128)
        n>>=7
    out.append(n)


def compact(state):
    arm,t,files,hist,last=state
    assert arm=='lru' and not hist and not last
    header=bytearray()
    varint(t,header);varint(len(files),header)
    texts=[]
    for path,info,runs in files:
        data=path.encode('utf8','surrogatepass')
        varint(len(data),header);header.extend(data)
        assert len(info)==2
        for v in info:varint(v,header)
        varint(len(runs),header)
        end=0
        for start,when,lines in runs:
            varint(start-end,header);varint(t-when,header);varint(len(lines),header)
            end=start+len(lines)
            for s in lines:
                body=s.lstrip(' ')
                varint(len(s)-len(body),header)
                texts.append(body.replace('\0','\0z').replace('\n','\0n'))
    header.extend('\n'.join(texts).encode('utf8','surrogatepass'))
    return b'V6'+zstd.compress(header,15,zstd_dict=lib.ZDICT)


def unpack(blob):
    if blob[:2]==b'R5':
        return old.decode(blob)
    assert blob[:2]==b'V6'
    data=zstd.decompress(blob[2:],zstd_dict=lib.ZDICT)
    j=0
    def take():
        nonlocal j
        num=shift=0
        while True:
            v=data[j];j+=1
            num|=(v & 127)<<shift
            if v<128: return num
            shift+=7
    files=[]
    t=take()
    for _ in range(take()):
        size=take();p=data[j:j+size].decode('utf8','surrogatepass');j+=size
        info=[take(),take()];runs=[];end=0
        for _ in range(take()):
            start=end+take();when=t-take()
            spaces=[take() for _ in range(take())]
            runs.append([start,when,spaces]);end=start+len(spaces)
        files.append([p,info,runs])
    raw=data[j:].decode('utf8','surrogatepass')
    content=iter(raw.split('\n')) if files else iter(())
    for _,_,runs in files:
        for run in runs:
            run[2]=[' '*n+next(content).replace('\0n','\n').replace('\0z','\0') for n in run[2]]
    assert next(content,None) is None
    return ['lru',t,files,[],[]]


def candidates(state):
    return [old.encode(state,'zstd15','json'),old.encode(state,'zstd15','edges'),compact(state)]


def select(state,kind):
    if kind=='standard':return old.encode(state,'zstd15','json')
    if kind=='edges':return old.encode(state,'zstd15','edges')
    return min(candidates(state),key=len)
