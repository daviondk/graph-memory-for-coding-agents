"""One commit-level binary summary for all search notes; all hashed probes fail open to a read."""
import functools,hashlib,math,struct,zlib
@functools.lru_cache(maxsize=300000)
def hash3(path,sign,term):
    data=hashlib.blake2b(path.encode('utf8','surrogatepass')+b'\0'+sign.encode()+bytes.fromhex(term),digest_size=24,person=b's6-sketch').digest()
    return struct.unpack('<QQQ',data)
def vi(x):
    out=bytearray()
    while x>=128:out.append((x&127)|128);x>>=7
    out.append(x);return bytes(out)
class Sketch:
    def __init__(self,size,kind):
        self.bits=bytearray(size);self.kind=kind;self.count=kind in ('count','max')
        self.cells=size*(2 if self.count else 8)
    def add(self,p,s,t,v=1):
        for ix in set(k%self.cells for k in hash3(p,s,t)):
            if self.count:
                shift=4*(ix&1);pos=ix//2;before=(self.bits[pos]>>shift)&15
                n=min(15,v+before) if self.kind=='count' else min(15,max(v,before))
                self.bits[pos]=(self.bits[pos]&~(15<<shift))|(n<<shift)
            else:self.bits[ix//8]|=1<<(ix%8)
    def upper(self,p,s,t):
        ix=[k%self.cells for k in hash3(p,s,t)]
        if not self.count:return int(all(self.bits[i//8]&(1<<(i%8)) for i in ix))
        v=min((self.bits[i//2]>>(4*(i%2)))&15 for i in ix);return math.inf if v==15 else v
class Writer:
    def __init__(self,files,budget):
        self.arr={m:Sketch(budget,m) for m in ('touched','net','signed','count','max','levels','flips')}
        self.delta={};self.live=[f['p'] for f in files if f['new_bytes']>0]
        raw=bytearray()
        for i,f in enumerate(files):
            p=f['p'];net=f['net'];self.delta[p]=net
            if not net:continue
            raw.extend(vi(i)+vi(len(net)))
            for t,v in sorted(net.items()):
                raw.extend(bytes.fromhex(t)+vi(2*v if v>=0 else -2*v-1))
        self.exact_cost=len(zlib.compress(raw,9))
        for f in files:
            p=f['p']
            for t in f['touched']:self.arr['touched'].add(p,'',t)
            for t in f['flips']:self.arr['flips'].add(p,'',t)
            for t,v in f['net'].items():
                sign='+' if v>0 else '-';mag=abs(v)
                self.arr['net'].add(p,'',t);self.arr['signed'].add(p,sign,t)
                for m in ('count','max'):self.arr[m].add(p,sign,t,mag)
                if v>0:self.arr['levels'].add(p,'+',t)
                else:
                    for level in range(mag.bit_length()):self.arr['levels'].add(p,'-'+str(level),t)
        self.budget=budget
    def reads(self,method,q):
        t=q['t'];prior=q['prior']
        if method=='all':return self.live
        if method=='ignore':return []
        if method=='hybrid':method='exact' if self.exact_cost<=self.budget else 'levels'
        selected=[]
        for p in self.live:
            n=prior.get(p,0);sign='-' if n else '+'
            if method=='exact':
                if (n+self.delta[p].get(t,0)>0)!=(n>0):selected.append(p)
                continue
            sketch=self.arr[method]
            if method in ('count','max'):v=sketch.upper(p,sign,t)>=max(1,n)
            elif method=='levels':v=sketch.upper(p,'-'+str(n.bit_length()-1) if n else '+',t)
            elif method=='signed':v=sketch.upper(p,sign,t)
            else:v=sketch.upper(p,'',t)
            if v:selected.append(p)
        return selected
METHODS=('all','ignore','touched','net','signed','count','max','levels','hybrid','flips','exact','subscriptions')
