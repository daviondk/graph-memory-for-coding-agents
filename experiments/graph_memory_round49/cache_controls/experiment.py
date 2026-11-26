"""Paired replay of preregistered cache policies across two repository-disjoint panels."""
from pathlib import Path
from collections import defaultdict
import hashlib, gzip, json, sys
import numpy as np
from policies import S3FIFO, Sieve, Lru
D = Path(__file__).resolve().parent
A = D.parents[1] / 'graph_memory_round48/cache_admission'
L = D.parent / 'long_gpu'
sys.path.insert(0, str(A))
from admission import Cache
from gdsf import GD
PLAN = '5a2dc741b468a4bd69f329d96f24bb3406ea3cb4b1360a7f630d1b72314d07f8'
CLASSES = {'s3':S3FIFO, 'sieve':Sieve, 'lru':Lru}
METHODS = {'batch':['proposed','cost','gdsf','lru_costhot','s3','s3_costhot','sieve','sieve_costhot'],
           'stream':['proposed','lru','s3','sieve'], 'stream_reverse':['proposed','lru','s3','sieve']}


def read(p):
    data = p.read_bytes()
    return json.loads(gzip.decompress(data) if p.suffix == '.gz' else data)


def dump(name, value):
    data = json.dumps(value, sort_keys=True, separators=(',',':'), allow_nan=False).encode() + b'\n'
    (D/name).write_bytes(gzip.compress(data, mtime=0) if name.endswith('.gz') else data)


class Keys:
    def __getitem__(self, key): return bytes.fromhex(key)


class IntKeys:
    def __getitem__(self, key): return int(key,16)


def panels():
    w = read(A/'workload.json.gz')
    digests = read(A/'key-digests.json.gz')
    r48 = {}
    for q,z in w['rows'].items():
        docs = {digests[str(k)]:z['docs'][str(k)] for k in z['order']}
        r48[q] = (docs,z['repo'],z['tokens'],w['pre'][q])
    r49 = {}
    truth = read(L/'transfer-outcomes.json.gz')
    for q,z in read(L/'transfer-inputs.json.gz').items():
        t = truth[q]
        r49[q] = (dict(z['docs']),z['repo'],t['total'],t['prior'])
    assert not r49.keys() & r48.keys()
    assert not {v[1] for v in r49.values()} & {v[1] for v in r48.values()}
    return {'R48':r48,'R49':r49}


def scheduler(keys, docs, old, hot):
    if not hot: return keys
    return sorted(keys, key=lambda k:(k in old, docs[k], -int(k,16)))


def replay(trace, interface, name):
    tag = name.split('_')[0]
    policy = CLASSES[tag]() if tag in CLASSES else GD('batch',31,IntKeys()) if tag=='gdsf' else Cache(tag,31,Keys())
    for current in trace:
        keys = list(current)
        if interface == 'stream_reverse': keys.reverse()
        if tag in CLASSES:
            old = policy.residents()
            served = set()
            for k in scheduler(keys,current,old,name.endswith('_costhot')):
                hit = policy.access(k)
                if (k in old if interface=='batch' else hit): served.add(k)
            saved = sum(current[k] for k in served)
            hits = len(served)
        elif interface == 'batch':
            hits,saved = policy.update(current) if tag=='gdsf' else policy.operate(current)
        else:
            hits = saved = 0
            for k in keys:
                n,t = policy.operate({k:current[k]})
                hits += n
                saved += t
    return [hits,saved]


def aggregate(obs):
    repos = sorted({z['repo'] for z in obs.values()})
    groups = {r:[v for v in obs.values() if v['repo']==r] for r in repos}
    n = len(repos)
    bs = np.random.default_rng(491902).multinomial(n,np.full(n,1/n),size=20000)
    den = np.array([sum(z['total'] for z in groups[r]) for r in repos])
    out = {}
    for field,names in METHODS.items():
        aa = {}
        vectors = {a:np.array([sum(z[field][a][1] for z in groups[r]) for r in repos]) for a in names}
        for a in names:
            v = vectors[a]
            delta = vectors['proposed'] - v
            aa[a] = dict(net=int(den.sum())-sum(z['within'] for z in obs.values())-int(v.sum()), hits=sum(z[field][a][0] for z in obs.values()),saved=int(v.sum()),
                fraction=v.sum()/den.sum(),macro=np.mean(v/den),diff=int(delta.sum()),
                delta=delta.sum()/den.sum(),macro_delta=np.mean(delta/den),
                ci=np.quantile((bs@delta)/(bs@den),[.025,.975]).tolist())
        out[field] = aa
    return dict(states=len(obs),repos=n,total=int(den.sum()),conditions=out)


def main():
    assert hashlib.sha256((D/'PROTOCOL_RU.md').read_bytes()).hexdigest() == PLAN
    assert read(D/'reference.json')['requests'] == 22344
    summary = {}
    for name,rows in panels().items():
        obs = {}
        if name == 'R48':
            inv=read(A.parent/'embedding_reuse/inventory.json.gz')
            intra={q:sum(row[1] for row in z['docs'])-sum(dict((k[0],k[1]) for k in z['docs']).values()) for q,z in inv.items()}
        else:
            intra={q:z['within'] for q,z in read(L/'transfer-outcomes.json.gz').items()}
        for q,(unit,repo,total,pre) in rows.items():
            seq = [rows[k][0] for k in pre]+[unit]
            obs[q] = {'repo':repo,'total':total,'within':intra[q]}
            for mode,methods in METHODS.items():
                obs[q][mode] = {m:replay(seq,mode,m) for m in methods}
        if name == 'R49':
            ref = read(L/'transfer-outcomes.json.gz')
            for q,z in obs.items():
                for m,b in [('proposed','proposed'),('lru_costhot','lru'),('gdsf','gdsf')]:
                    a=ref[q]['arm'][b]
                    assert z['batch'][m]==[a['hits'],a['inter']]
        else:
            ref=read(A/'order-outcomes.json.gz')
            for q,z in obs.items():
                assert z['batch']['proposed'][1]==ref['original'][q]['proposed']
                assert z['batch']['lru_costhot'][1]==ref['cost_hot_last'][q]['hot_lru']
        dump(name+'-outcomes.json.gz',obs)
        summary[name]=aggregate(obs)
    dump('results.json',summary)
    print({p:{m:round(100*x['delta'],3) for m,x in v['conditions']['batch'].items()} for p,v in summary.items()})


if __name__ == '__main__': main()

