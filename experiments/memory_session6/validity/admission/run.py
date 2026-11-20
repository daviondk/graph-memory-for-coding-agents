from common import *
from policies import Cache
def run(outpath):
    split=splitmap()
    with outpath.open('wb') as dest,gzip.GzipFile(filename='',fileobj=dest,mode='wb',mtime=0,compresslevel=6) as out:
        for r in rows(INPUT):
            states={(kind,k,p):Cache(p,k) for kind in ('cmd','id') for k in (1,2,4) for p in NAMES}
            dec=[];previous=0;prev_tick=-1
            for tick,edits,cmd,terms in r['literal_calls']:
                assert tick>prev_tick and edits>=previous and terms
                groups={'cmd':[cmd],'id':sorted(set(terms))}
                log=[]
                for kind,ks in groups.items():
                    for k in (1,2,4):
                        for p in NAMES:
                            log.append(states[kind,k,p].obs(ks,edits>previous))
                dec.append([tick,edits,log]);previous=edits;prev_tick=tick
            z=[r['shard'],r['row'],r['messages_sha'],r['repo'],split[r['repo']],dec]
            out.write((canon(z)+'\n').encode())
def main():
    if not (ROOT/'design_lock.json').exists():
        write('design_lock.json',dict(created=stamp(),source_sha=digest(INPUT.read_bytes()),hashes=hashes(['PROTOCOL.md','common.py','policies.py','run.py','grade.py']),split=splitmap()))
    sourcecheck();run(ROOT/'decisions.jsonl.gz')
    write('decision_lock.json',dict(created=stamp(),decisions_sha=digest((ROOT/'decisions.jsonl.gz').read_bytes()),design_sha=digest((ROOT/'design_lock.json').read_bytes())))
if __name__=='__main__':main()

