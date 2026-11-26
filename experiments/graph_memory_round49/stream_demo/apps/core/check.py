"""Exercise each registered example over HTTP and brute-force strict fixing on small tails."""
from contextlib import contextmanager
import itertools,json,random,sys,subprocess,hashlib,sqlite3
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen,Request
from urllib.error import HTTPError
from core_view import BASE,dynamic,reduce,prefix
@contextmanager
def launch():
    p=subprocess.Popen([sys.executable,'-B',str(BASE/'core_view.py'),'--port','0'],stdout=subprocess.PIPE,text=True)
    try:
        host=p.stdout.readline().strip();assert host.startswith('http://127.0.0.1:') and host.split(':')[-1].isdigit()
        yield host
    finally:
        p.terminate();p.wait(timeout=8)
def main():
    source=json.loads((BASE/'projection.json').read_bytes())
    assert hashlib.sha256((BASE/'core.sqlite').read_bytes()).hexdigest()==source['sqlite']
    count=0
    with launch() as host:
        assert urlopen(host+'/').geturl()==host+'/core'
        assert b'Learned packet' in urlopen(host+'/core').read()
        cases=json.load(urlopen(host+'/core/catalog'))['cases'];assert len(cases)==3
        for row in cases:
            for s,g in itertools.product([25,50,75,100],['greedy','previous']):
                p=dict(case=row['name'],step=s,policy=g);q=urlencode(p)
                bare=json.load(urlopen(host+'/core/api?'+q));assert 'audit' not in bare
                direct=json.load(urlopen(Request(host+'/core/api',data=json.dumps(p).encode(),headers={'Content-Type':'application/json'})));assert bare==direct
                check=json.load(urlopen(host+'/core/audit?'+q));a=check.pop('audit');assert a['equal'] and a['full_order']==bare['packet'] and bare==check
                assert sum(len(bare[k]) for k in ('forced','rejected','core'))==bare['eligible_tail']
                assert bare['lower_q32']*bare['upper_den']<=bare['objective_q32']*bare['upper_den']<=bare['upper_num']
                count+=1
        for url,code in [('/none',404),('/core/api?step=-1',400),('/core/audit?policy=oracle',400)]:
            try:urlopen(host+url);raise AssertionError(url)
            except HTTPError as err:assert err.code==code
    rng=random.Random(490661)
    for j in range(250):
        items=[(0,1024,13)]+[(i,rng.choice([0,170,341,512,690,1024,1536]),rng.randrange(4)) for i in range(1,11)]
        h,t,r=prefix(items);allowed=[k for k in t if k[1]<=r]
        optimal=None
        for mask in range(1<<len(allowed)):
            chosen=[v for i,v in enumerate(allowed) if mask&(1<<i)]
            if sum(x[1] for x in chosen)>r:continue
            key=sum(x[2] for x in chosen),-mask
            if optimal is None or key>optimal[0]:optimal=key,[x[0] for x in h+chosen]
        assert reduce(items,{i for i in range(11) if rng.randrange(2)},True)['packet']==optimal[1]
    print('Passing:',count,'observed cases x 3 HTTP responses, three rejected requests, 250 exhaustive tied/zero-cost pools.')
if __name__=='__main__':main()
