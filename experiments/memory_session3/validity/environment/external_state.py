"""Ground-truth environment-shift stress test and access-based observation invalidation."""
import collections,csv,importlib.util,json,os,subprocess,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
sys.path.insert(0,str(ROOT))
from sources import canon,save,sha,tree
from score import counts
VERS={'wcwidth':'0.2.13','idna':'3.10','packaging':'25.0','humanize':'4.11.0'}
PROFILES=[{}, {'MEMORY_TRIAL_MARKER':'one'}, {'UNICODE_VERSION':'4.1.0'}, {'UNICODE_VERSION':'4.1.0','MEMORY_TRIAL_MARKER':'one'}]
VARIED=set.union(*(set(p) for p in PROFILES))
def read(p):return json.loads(p.read_text(encoding='utf8'))
def observers():
    rows=read(ROOT/'roster.json')+read(ROOT/'external_validation/roster.json')
    rows=[r for r in rows if r['pkg'] in VERS]
    for cp in range(0x1f300,0x1fb00,17):
        for fn,text in [('wcwidth',chr(cp)),('wcswidth','A'+chr(cp))]:
            row={'pkg':'wcwidth','module':'','function':fn,'args':[text],'kwargs':{},'format':'plain'}
            row['key']='stress-'+sha(canon(row).encode())[:14];rows.append(row)
    return rows
def worker(pkg,profile,mode):
    base=ROOT/'external_validation' if pkg=='humanize' else ROOT
    spec=importlib.util.spec_from_file_location('obs',base/'observe.py')
    ob=importlib.util.module_from_spec(spec);spec.loader.exec_module(ob)
    sys.path.insert(0,str(tree(pkg,VERS[pkg])))
    records=[];cls=type(os.environ); original=cls.__getitem__
    for r in read(HERE/'roster.json'):
        if r['pkg']!=pkg:continue
        ob.clean(pkg);keys=set()
        def tracked(self,key):
            if self is os.environ:keys.add(key)
            return original(self,key)
        if mode=='trace':cls.__getitem__=tracked
        start=time.perf_counter_ns()
        try:
            try:fn=ob.resolve(r)
            except AttributeError:fn=None
            value=ob.value(r,fn)
        finally:cls.__getitem__=original
        records.append({'key':r['key'],'value':value,'env_reads':sorted(keys),'ns':time.perf_counter_ns()-start})
    save(HERE/'runs'/f'{pkg}-{profile}-{mode}.json',records)
def evaluate():
    data={};masks=[];sigs=collections.defaultdict(collections.Counter);timing=collections.Counter()
    for pkg in VERS:
        for p in range(len(PROFILES)):
            trace=read(HERE/'runs'/f'{pkg}-{p}-trace.json')
            for r in trace:
                data[pkg,p,r['key']]=r
                sigs[pkg].update(r['env_reads']);timing['traced_ns']+=r['ns']
        for i,old in enumerate(PROFILES):
            for j in range(i+1,len(PROFILES)):
                new=PROFILES[j];changes={k for k in VARIED if old.get(k)!=new.get(k)}
                for r in read(HERE/'runs'/f'{pkg}-{i}-trace.json'):
                    masks.append({'pkg':pkg,'old':i,'new':j,'key':r['key'],'unicode_changed':'UNICODE_VERSION' in changes,
                                  'replay':False,'same_source':True,'full_environment':not changes,'observed_env':not set(r['env_reads'])&changes})
    def write(path,rows):
        with path.open('w',encoding='utf8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    write(HERE/'decisions.csv',masks)
    save(HERE/'lock.json',{'sha256':{n:sha((HERE/n).read_bytes()) for n in ['PROTOCOL.md','external_state.py','roster.json','decisions.csv']}})
    plain={}
    for pkg in VERS:
        for i in range(4):
            for r in read(HERE/'runs'/f'{pkg}-{i}-plain.json'):
                identity=(pkg,i,r['key'])
                assert data[identity]['value']==r['value']
                plain[identity]=r['value'];timing['plain_ns']+=r['ns']
    groups=collections.defaultdict(list)
    for r in masks:
        p,k,i,j=r['pkg'],r['key'],r['old'],r['new']
        r['changed']=int(plain[p,i,k]!=plain[p,j,k])
        for label in ['all',p,'unicode_change='+str(r['unicode_changed'])]:groups[label].append(r)
    write(HERE/'per_check.csv',masks)
    result={g:{m:counts(rs,m) for m in ('replay','same_source','full_environment','observed_env')} for g,rs in groups.items()}
    save(HERE/'results.json',{'groups':result,'access_counts':sigs,'timing':timing})
    print(result['all'])
def main():
    if len(sys.argv)>1:worker(sys.argv[1],int(sys.argv[2]),sys.argv[3]);return
    save(HERE/'roster.json',observers())
    (HERE/'runs').mkdir(exist_ok=True)
    for pkg in VERS:
        for i,p in enumerate(PROFILES):
            modes=['plain','trace'] if (i+len(pkg))%2==0 else ['trace','plain']
            for mode in modes:
                env={k:v for k,v in os.environ.items() if k not in VARIED}
                env.update(p);env.update(PYTHONHASHSEED='0',PYTHONUTF8='1')
                subprocess.run([sys.executable,'-S',__file__,pkg,str(i),mode],env=env,check=True,timeout=75)
    evaluate()
if __name__=='__main__':main()
