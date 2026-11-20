from prepare import *
def main():
    data=json.loads((ROOT/'real_intents.json').read_bytes());reps=json.loads((ROOT/'source_lock.json').read_bytes());folder=ROOT/'natural';folder.mkdir(exist_ok=True)
    summary={}
    for repo,inputs in data['queries'].items():
        p=ROOT/'mirrors'/repo.replace('/','__');bs=Blobs(p);words={r['word'] for r in inputs}
        pairs=[];g=[]
        for step,(old,new) in enumerate(zip(reps[repo]['commits'],reps[repo]['commits'][1:])):
            if not step:continue
            ts=pick(words,repo+'|'+old+'|a',24)
            def readrev(rev):
                files=tree(p,rev);z={w:{} for w in ts}
                for f,oid in files.items():
                    c,_=bs.get(oid)
                    for w in ts:
                        if c[w]:z[w][f]=c[w]
                return z
            prev=readrev(old);cur=readrev(new)
            pairs.append({'repo':repo,'step':step,'queries':[{'arm':'agent','t':key(w),'length':len(w.encode()),'prior':prev[w]} for w in ts]})
            g.append({'repo':repo,'step':step,'result':{key(w):sorted(cur[w]) for w in ts}})
        bs.close();name=repo.replace('/','__');summary[repo]=[len(words),sum(len(row['queries']) for row in pairs)]
        for name2,dat in [('inputs',pairs),('gold',g)]:
            (folder/(name+'_'+name2+'.gz')).write_bytes(gzip.compress(('\n'.join(map(emit,dat))+'\n').encode(),mtime=0))
    (folder/'coverage.json').write_text(json.dumps(summary,indent=1));print(summary)
if __name__=='__main__':main()
