"""Produce a redacted audit of context-only action grammar before removing task downloads."""
import gzip,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT.parent))
from evaluate import actions,choose,TARGETS
from project import project
from fetch import SPLITS
def main():
    n=0
    with (ROOT/'history_actions.jsonl.gz').open('wb') as fp,gzip.GzipFile(fileobj=fp,mode='wb',mtime=0,filename='') as out:
        for s in SPLITS[1:]:
            with gzip.open(ROOT.parent/'raw'/(s+'.json.gz'),'rt',encoding='utf8') as src:
                for line in src:
                    obj=json.loads(line);r=project(obj)
                    if r['k'] not in TARGETS or not r['y']:continue
                    atoms=[]
                    for k,args in actions(obj.get('action_history') or ''):
                        if k=='load' or k in TARGETS:
                            import re
                            match=re.search(r'\buid="([A-Za-z0-9_-]+)"',args)
                            atoms.append([k,match.group(1) if match else None])
                    rec={'s':s,'d':r['demo'],'i':r['turn'],'actions':atoms}
                    out.write((json.dumps(rec,separators=(',',':'))+'\n').encode());n+=1
    path=ROOT/'history_actions.jsonl.gz'
    (ROOT/'projection_lock.json').write_text(json.dumps({'history_actions.jsonl.gz':hashlib.sha256(path.read_bytes()).hexdigest(),'project_history.py':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}))
    print('context-only redacted projections',n)
if __name__=='__main__':main()

