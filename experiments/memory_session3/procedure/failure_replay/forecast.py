"""Frozen forecasts. A prediction is emitted before any current result is passed to update()."""
from collections import OrderedDict
import gzip,hashlib,json,re,sys,shlex
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
from replay import parse_read,split_cwd,effect
def sha(x):return hashlib.sha256(x).hexdigest()
def dump(x):return json.dumps(x,ensure_ascii=True,separators=(',',':'))
def ro(cmd):
    cwd,b=split_cwd(cmd)
    if not cwd or not (cwd=='/testbed' or cwd.startswith('/testbed/')):return False
    if parse_read(cmd):return True
    if re.search(r'[\n\r;|<>$&`\\*?(){}]',b):return False
    try:parts=shlex.split(b)
    except ValueError:return False
    if not parts:return False
    hd,*args=parts
    if hd=='pwd':return len(args)==0
    if hd not in ['ls','grep','rg']:return False
    for a in args:
        if a.startswith('/') and not a.startswith('/testbed/'):return False
        if a.startswith('-') and not (a=='--' or re.fullmatch('-[alhRdi1]+',a) and hd=='ls' or re.fullmatch('-[nrilHFsweqvIoEhR]+',a) and hd in ['rg','grep'] or a in ['--files','--hidden','--no-heading','--files-with-matches','--fixed-strings','--line-number','--no-filename','--ignore-case'] and hd in ['rg','grep']):return False
    return True
def known_write(cmd,rc):
    if rc:return False
    if effect(cmd)[0]=='edit':return True
    return bool(re.match(r'^(?:cat\s+>\s*[\w./-]+\s*<<|sed\s+-i(?:\s|\x27|\x22)|touch\s+[\w./-]+$)',cmd.strip()))
class Policy:
    def __init__(self):
        self.guard={n:OrderedDict() for n in [1,8]}
        self.stale=OrderedDict();self.any={};self.last=None;self.barrier=-1;self.write=-1
        self.read_digest={};self.change_witness=-1
    def forecast(self,i,cmd):
        if not cmd:return {}
        nodes={'adjacent':self.last if self.last and self.last['key']==cmd else None,'guard1':self.guard[1].get(cmd),'guard8':self.guard[8].get(cmd),'stale8':self.stale.get(cmd),'history':self.any.get(cmd)}
        result={}
        for k,v in nodes.items():
            if not v:continue
            idx=v['group']
            result[k]={'at':idx,'pred_rc':v['rc'],'pred_sha':v['sha'],'current_readonly':ro(cmd),'lag':i-idx,'context':'adjacent' if idx==i-1 else ('readonly' if self.barrier<=idx else 'opaque'),'past_write':self.write>idx,'observed_content_change':self.change_witness>=idx}
        return result
    def ambiguous(self,grp,i):
        for cache in self.guard.values():cache.clear()
        for e in grp:
            self.stale.pop(e['command'],None);self.any.pop(e['command'],None)
        self.last=None;self.barrier=i
    def update(self,i,cmd,y):
        if not cmd or y is None:
            self.ambiguous([{'command':cmd}],i);return
        is_ro=ro(cmd);self.last=None
        if not is_ro:
            self.barrier=i
            for c in self.guard.values():c.clear()
        rc=y['rc']
        if known_write(cmd,rc):self.write=i
        if parse_read(cmd) and rc==0 and y['visible']:
            prior=self.read_digest.get(cmd)
            if prior and prior[0]!=y['sha']:self.change_witness=max(self.change_witness,prior[1])
            self.read_digest[cmd]=(y['sha'],i)
        for c in [*self.guard.values(),self.stale,self.any]:c.pop(cmd,None)
        if rc!=0 and y['visible']:
            v={'key':cmd,'group':i,'rc':rc,'sha':y['sha']};self.last=v
            for c,cap in [(self.guard[1],1),(self.guard[8],8),(self.stale,8),(self.any,None)]:
                c[cmd]=v
                if cap is not None and len(c)>cap:c.popitem(last=False)
def main():
    m=json.loads((ROOT.parent/'projected_manifest.json').read_bytes()); stats={'sessions':0,'calls':0,'groups':0,'ambiguous_calls':0,'single':0}
    with gzip.open(ROOT/'predictions.jsonl.gz','wt',encoding='utf8') as f:
        for name,h in sorted(m.items()):
            path=ROOT.parent/name;raw=path.read_bytes();assert sha(raw)==h
            x=json.loads(gzip.decompress(raw));p=Policy();stats['sessions']+=1
            for i,g in enumerate(x['groups']):
                stats['groups']+=1;stats['calls']+=len(g)
                if len(g)!=1:p.ambiguous(g,i);stats['ambiguous_calls']+=len(g);continue
                e=g[0];cmd=e['command'];stats['single']+=1
                z=p.forecast(i,cmd)
                if z:f.write(dump({'model':x['source']['model'],'issue':x['source']['id'],'group':i,'cmd_sha':sha(cmd.encode()),'preds':z})+'\n')
                p.update(i,cmd,e['result'])
    fs=['PROTOCOL.md','forecast.py','predictions.jsonl.gz','../projected_manifest.json','../sources.py','../replay.py']
    lock={'sha256':{n:sha((ROOT/n).read_bytes()) for n in fs},'stats':stats}
    (ROOT/'prediction_lock.json').write_text(json.dumps(lock,indent=1),encoding='utf8');print(stats)
if __name__=='__main__':main()

