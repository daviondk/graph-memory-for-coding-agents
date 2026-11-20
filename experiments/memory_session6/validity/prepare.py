"""Project public Git history into label-free diffs, prior answers and separately sealed ground truth."""
import collections,concurrent.futures,functools,gzip,hashlib,json,keyword,re,shlex,subprocess
from pathlib import Path
from fetch import ROOT,git
WORD=re.compile(rb'[A-Za-z_][A-Za-z_0-9]*')
ID=re.compile(r'^[A-Za-z_][A-Za-z_0-9]*$')
def h(s):return hashlib.sha256(s.encode()).hexdigest()
def emit(x):return json.dumps(x,ensure_ascii=True,separators=(',',':'))
def eligible(t):return len(t)>=3 and not keyword.iskeyword(t) and not t.startswith('__')
@functools.lru_cache(maxsize=250000)
def key(t):return hashlib.blake2b(t.encode(),digest_size=12,person=b's6-identifier').hexdigest()
def words(raw):return collections.Counter(t.decode('ascii') for t in WORD.findall(raw))
def tree(repo,rev):
    m={}
    for line in git(repo,'ls-tree','-rz',rev).split(b'\0'):
        if not line:continue
        meta,name=line.split(b'\t',1);mode,kind,oid=meta.split()
        if name.endswith(b'.py') and mode in (b'100644',b'100755'):m[name.decode('utf8','surrogateescape')]=oid
    return m
class Blobs:
    def __init__(self,p):
        self.proc=subprocess.Popen(['git','-C',str(p),'cat-file','--batch'],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
        self.cache={}
    def get(self,oid):
        if not oid:return collections.Counter(),0
        if oid not in self.cache:
            f=self.proc;f.stdin.write(oid+b'\n');f.stdin.flush()
            _,kind,n=f.stdout.readline().split();assert kind==b'blob'
            data=f.stdout.read(int(n));assert len(data)==int(n) and f.stdout.read(1)==b'\n'
            self.cache[oid]=(words(data),len(data))
        return self.cache[oid]
    def close(self):
        self.proc.stdin.close();self.proc.wait(timeout=30)
def old_queries():
    p=ROOT.parents[1]/'memory_session5/packets';sets=collections.defaultdict(set);seen=0;files={}
    for pattern in ('source/train/*.gz','source/test/*.gz','transfer/source/*.gz','allocation/source/*.gz'):
        for f in sorted(p.glob(pattern)):
            files[f.relative_to(p).as_posix()]=hashlib.sha256(f.read_bytes()).hexdigest()
            with gzip.open(f,'rt',encoding='utf-8') as it:
                for ln in it:
                    row=json.loads(ln);repo=row['instance'].split('.')[0].replace('__','/').lower()
                    for name,args,_ in row['events']:
                        if name!='bash' or not isinstance(args,dict):continue
                        cmd=args.get('command') or ''
                        for seg in re.split(r'(?:&&|\|\||[;|\n])',cmd):
                            try:v=shlex.split(seg)
                            except ValueError:continue
                            if not v or v[0] not in ('grep','rg'):continue
                            seen+=1;i=1
                            while i<len(v) and v[i].startswith('-'):
                                if v[i] in ('-e','--regexp'):i+=1;break
                                if v[i] in ('-g','--glob','-t','--type','--include','--exclude','-A','-B','-C','-m'):i+=2
                                else:i+=1
                            if i<len(v) and ID.fullmatch(v[i]) and eligible(v[i]):sets[repo].add(v[i])
    (ROOT/'intent_receipt.json').write_text(json.dumps({'sources':files,'simple_grep_commands_seen':seen,'unique_extracted':{k:len(v) for k,v in sets.items()}},indent=1))
    return sets
def dpath(line):
    val=line[4:].split(b'\t')[0]
    if val==b'/dev/null':return None
    if val.startswith(b'"'):raise ValueError('unexpected quoted path in Git diff')
    return val[2:].decode('utf8','surrogateescape')
def patch(p,old,new,prev,curr):
    raw=git(p,'-c','core.quotePath=false','diff','--text','--no-ext-diff','--no-textconv','--no-color','--no-renames','--unified=0',old,new,'--','*.py')
    table={};a=b=None;hunk=False;span=0
    for ln in raw.split(b'\n'):
        if ln.startswith(b'diff --git '):a=b=None;hunk=False;continue
        if not hunk and ln.startswith(b'--- '):a=dpath(ln);continue
        if not hunk and ln.startswith(b'+++ '):b=dpath(ln);continue
        if ln.startswith(b'@@ '):hunk=True;continue
        if not hunk or ln[:1] not in (b'+',b'-'):continue
        sign=ln[0]==43;k=b if sign else a
        if k is None or k not in (curr if sign else prev):continue
        adds,dels=table.setdefault(k,(collections.Counter(),collections.Counter()))
        (adds if sign else dels).update(words(ln[1:]));span+=len(ln[1:])+1
    return table,len(raw),span
def pick(v,salt,n=12):return sorted(v,key=lambda x:h(salt+'|'+x))[:n]
def run(repo,info,intents):
    p=ROOT/'mirrors'/repo.replace('/','__');dest=ROOT/'projection';dest.mkdir(exist_ok=True);side=ROOT/'gold';side.mkdir(exist_ok=True)
    name=repo.replace('/','__')+'.jsonl.gz';bs=Blobs(p);commits=info['commits'];prev=tree(p,commits[0]);previous_vocab=set();counts=collections.Counter()
    def hashed(d):return {key(k):v for k,v in sorted(d.items())}
    with gzip.open(dest/name,'wt',encoding='utf8',compresslevel=3) as doc,gzip.open(side/name,'wt',encoding='utf8') as gold:
        for step,(old,new) in enumerate(zip(commits,commits[1:])):
            curr=tree(p,new);delta,patchbytes,span=patch(p,old,new,prev,curr)
            changed=sorted(k for k in prev.keys()|curr.keys() if prev.get(k)!=curr.get(k))
            rows=[];this_vocab=set()
            for f in changed:
                oc,ob=bs.get(prev.get(f));nc,nb=bs.get(curr.get(f));adds,dels=delta.get(f,({},{}))
                touched=set(adds)|set(dels)
                net={t:adds.get(t,0)-dels.get(t,0) for t in touched if adds.get(t,0)!=dels.get(t,0)}
                if {t:nc[t]-oc[t] for t in oc.keys()|nc.keys() if nc[t]!=oc[t]}!=net:raise ValueError((repo,step,f,'diff verification failed'))
                flips=set(oc)^set(nc);assert flips.issubset(net)
                rows.append({'p':f,'old_bytes':ob,'new_bytes':nb,'touched':sorted(key(t) for t in touched),'net':hashed(net),'flips':sorted(key(t) for t in flips)})
                this_vocab.update(t for t in touched if eligible(t))
            if step>0:
                before={f:bs.get(o)[0] for f,o in prev.items()};after={f:bs.get(o)[0] for f,o in curr.items()}
                vocab=set().union(*(x.keys() for x in before.values()))
                s=repo+'|'+old;groups={'recent':pick(previous_vocab,s+'|r'),'background':pick((x for x in vocab if eligible(x) and x not in previous_vocab),s+'|b'),'agent':pick(intents,s+'|a',24)}
                queries=[];gs={}
                for tag,qs in groups.items():
                    for t in qs:
                        old_counts={f:x[t] for f,x in before.items() if x[t]}
                        queries.append({'arm':tag,'t':key(t),'length':len(t.encode()),'prior':old_counts})
                        gs[key(t)]=sorted(f for f,x in after.items() if x[t])
                rec={'repo':repo,'before':old,'after':new,'step':step,'files':rows,'patch_bytes':patchbytes,'edited_line_bytes':span,'queries':queries,'tree_files':len(curr)}
                assert len({key(t) for t in vocab})==len(vocab)
                doc.write(emit(rec)+'\n');gold.write(emit({'repo':repo,'step':step,'result':gs})+'\n')
                counts.update({tag:len(ls) for tag,ls in groups.items()});counts['commits']+=1;counts['changed_paths']+=len(changed)
            previous_vocab=this_vocab;prev=curr
    bs.close();print(repo,dict(counts),flush=True);return repo,dict(counts)
def main():
    intents=old_queries();info=json.loads((ROOT/'source_lock.json').read_bytes())
    # Sequential input projection bounds memory in repositories with large Python trees.
    stats=dict(run(r,v,intents.get(r.lower(),set())) for r,v in info.items())
    (ROOT/'projection_stats.json').write_text(json.dumps(stats,indent=2))
    files=[ROOT/'PROTOCOL.md',ROOT/'source_lock.json',ROOT/'prepare.py',*sorted((ROOT/'projection').glob('*.gz')),*sorted((ROOT/'gold').glob('*.gz'))]
    (ROOT/'projection_lock.json').write_text(json.dumps({f.relative_to(ROOT).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in files},indent=2))
if __name__=='__main__':main()
