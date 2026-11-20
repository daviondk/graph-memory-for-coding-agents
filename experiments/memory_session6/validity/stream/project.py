import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from prepare import Blobs,ROOT,tree,patch,emit,pick,key
import hashlib,json,gzip
BASE=ROOT/'stream'
def main():
    intent=json.loads((ROOT/'real_intents.json').read_bytes())['queries'];chosen={}
    for repo,cs in json.loads((BASE/'source_lock.json').read_bytes()).items():
        p=ROOT/'mirrors'/repo.replace('/','__');b=Blobs(p);prev=tree(p,cs[0])
        words=pick({r['word'] for r in intent[repo]},'s6-watchlist|'+repo,24)
        lookup={w:key(w) for w in words};before={lookup[w]:{} for w in words}
        for f,oid in prev.items():
            c,_=b.get(oid)
            for w in words:
                if c[w]:before[lookup[w]][f]=c[w]
        chosen[repo]={'watch':[{ 'key':lookup[w], 'chars':len(w)} for w in words],'initial_counts':before,'initial_paths':len(prev)}
        d=[];g=[]
        for old,new in zip(cs,cs[1:]):
            cur=tree(p,new);table,byt,span=patch(p,old,new,prev,cur);files=[]
            for path in sorted(k for k in cur.keys()|prev.keys() if prev.get(k)!=cur.get(k)):
                add,rm=table.get(path,({},{}));nc,nb=b.get(cur.get(path));oc,ob=b.get(prev.get(path))
                net={w:add.get(w,0)-rm.get(w,0) for w in add.keys()|rm.keys() if add.get(w,0)!=rm.get(w,0)}
                assert {w:nc[w]-oc[w] for w in nc.keys()|oc.keys() if nc[w]!=oc[w]}==net
                files.append({'p':path,'oid':(cur.get(path) or b'').decode(),'new_bytes':nb,'net':{key(w):v for w,v in net.items()},'touched':[],'flips':[]})
            now={lookup[w]:{} for w in words}
            for f,oid in cur.items():
                c,_=b.get(oid)
                for w in words:
                    if c[w]:now[lookup[w]][f]=c[w]
            # Existing client knows the previous search. Readbacks use the independently projected current source.
            d.append({'old':old,'new':new,'patch_bytes':byt,'line_bytes':span,'files':files})
            g.append(now);prev=cur
        b.close()
        for tag,data in [('events',d),('truth',g)]:
            (BASE/(repo.replace('/','__')+'_'+tag+'.gz')).write_bytes(gzip.compress(emit(data).encode(),mtime=0))
    (BASE/'initial.json.gz').write_bytes(gzip.compress(emit(chosen).encode(),mtime=0));print('disjoint transitions',sum(len(v)-1 for v in json.loads((BASE/'source_lock.json').read_bytes()).values()))
if __name__=='__main__':main()
