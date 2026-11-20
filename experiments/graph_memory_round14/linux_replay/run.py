"""Repeat sealed released-byte and controlled file observations on an actual Linux filesystem."""
import collections,contextlib,gzip,hashlib,json,os,platform,random,re,shutil,subprocess,sys,tempfile,time
from pathlib import Path
D=Path(__file__).resolve().parent;OLD=D.parent/"ledger"
sys.path.insert(0,str(OLD))
from audit import decode
from mcp import Client,wire
from operator import itemgetter

def load(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.name.endswith(".gz") else b)
def gz(p,records):
    p.write_bytes(gzip.compress(json.dumps(records,ensure_ascii=False,separators=(",",":")).encode(),mtime=0))
def h(x):return hashlib.sha256(x).hexdigest()
def snapshot(p):
    s=p.stat()
    return [s.st_mtime_ns,s.st_size,s.st_dev,s.st_ino,s.st_ctime_ns]
RULES={"mtime_size":2,"mtime_id":4,"ctime_id":5}

class FileServer(Client):
    def __init__(self,root,label,exe,trace=False):
        self.id=0;self.rows=[]
        self.stderr=open(root/(label+".stderr"),"wb")
        command=[str(exe),"mcp","--path",str(root)]
        if trace:
            command=[str(D/"vendor"/"strace"),"-f","-qq","-ttt","-s","256","-yy",
               "-o",str(root/(label+".strace")),"-e","trace=open,openat,read,pread64,readv,stat,lstat,statx,newfstatat,fstat,close",*command]
        env={**os.environ,"TOKIO_WORKER_THREADS":"2","LD_LIBRARY_PATH":str(D/"vendor"/"lib")}
        self.proc=subprocess.Popen(command,cwd=root,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.stderr,env=env)
        cap={"experimental":{"session":{"session_id":label,"workdir":str(root),"context_epoch":1}}}
        self.ask("initialize",{"protocolVersion":"2025-11-25","capabilities":cap,"clientInfo":{"name":"obs-linux","version":"1"}})
        self.proc.stdin.write(wire({"jsonrpc":"2.0","method":"notifications/initialized"}));self.proc.stdin.flush()
    def view(self,*args,**kw):
        start=time.time_ns();result,row=super().view(*args,**kw);row["clock_open_ns"]=start;row["clock_close_ns"]=time.time_ns();return result,row

class Writer:
    def __init__(self,root):
        self.proc=subprocess.Popen([sys.executable,"-B",str(D/"writer.py"),str(root)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    def apply(self,p,kind,data):
        self.proc.stdin.write(json.dumps([p.name,kind,data.hex()])+"\n");self.proc.stdin.flush()
        assert self.proc.stdout.readline()=="ok\n"
    def close(self):
        self.proc.stdin.close();self.proc.wait(timeout=4)

def marker(old):
    return f"[unchanged since you last viewed or edited it (compared with the file on disk just now): {len(old.splitlines())} lines. Pass full: true to re-read, or view a line range.]"
def altered(old,case,i):
    if case=="append":return old+b"# external observation\n"
    if case=="prepend":return b"# external observation\n"+old
    if case.startswith("replace") or case=="atomic_restore":
        lines=old.splitlines(keepends=True);length=len(lines[i])-1
        lines[i]=(b"# observation"[:length]+b"."*length)[:length]+b"\n"
        return b"".join(lines)
    return old
def scenarios():
    ctrl=[]
    for state in load(OLD/"pair_states.json"):
        old=(OLD/state["fixture"]).read_bytes();new=altered(old,state["scenario"],state["lo"]+3)
        assert h(old)==state["old_sha"] and h(new)==state["new_sha"]
        ctrl.append(("controlled",state["case"],old,new,state["scenario"]))
    natural=[]
    for i,p in enumerate(load(OLD/"natural/released_pairs.json.gz")):
        if p["new"] is None:continue
        x=p["old"].encode();y=p["new"].encode()
        natural.append(("released",str(i),x,y,"write" if x!=y else "no_update"))
    return ctrl+natural
def sections(root):
    return subprocess.check_output(["stat","-f","-c","%T",str(root)]).decode().strip()

def run(fs,mount,tracing):
    with tempfile.TemporaryDirectory(prefix="r14-mem-linux-",dir=mount) as name:
        root=Path(name);actual=sections(root);assert (fs=="tmpfs" and actual=="tmpfs") or (fs=="ext4" and actual=="ext2/ext3")
        exe=root/"octofs";shutil.copyfile(D/"vendor/octofs",exe);exe.chmod(0o700)
        assert h(exe.read_bytes())==load(D/"linux_sources.json")["octofs"]["exe"]
        arms=["native","full",*RULES];sessions={a:FileServer(root,a,exe,tracing and a in ("native","ctime_id")) for a in arms}
        writer=Writer(root);bills=[];scores=[];stress=[];wins={}
        def call(arm,p,stage,case,old,index,**options):
            result,receipt=sessions[arm].view(p.name,**options)
            bills.append(dict(arm=arm,case=case,stage=stage,filename=p.name,**receipt))
            return result
        for i,(panel,case,old,new,change) in enumerate(scenarios()):
            key=panel+"|"+case
            p=root/f"case_{i:03}.py";p.write_bytes(old);saved={}
            for a in arms:
                initial=call(a,p,"original",key,b"",i);assert decode(initial,b"")==old
                if a in RULES:saved[a]=snapshot(p)
            writer.apply(p,change,new)
            assert p.read_bytes()==new
            after=snapshot(p);order=arms[:];random.Random(i+182).shuffle(order)
            for arm in order:
                start=time.perf_counter_ns();hit=False
                if arm in RULES:
                    now=snapshot(p);n=RULES[arm];hit=now[:n]==saved[arm][:n]
                if hit:txt=marker(old)
                else:txt=call(arm,p,"repeat",key,old,i,**({"full":True} if arm=="full" else {}))
                elapsed=time.perf_counter_ns()-start;head=decode(txt,old)
                scores.append(dict(panel=panel,case=case,arm=arm,hit=hit,actual=h(head),truth=h(new),before=h(old),cost=0 if hit else len(new),view=len(txt.encode()),elapsed_ns=elapsed,
                                   stored=saved.get(arm),after=after))
        if not tracing:
            seen=[]
            for state in load(OLD/"pair_states.json"):
                repo=state["fixture"].split("/")[1]
                if repo in [x[0] for x in seen]:continue
                if state["index"]%3:continue
                seen.append((repo,state))
            assert len(seen)==4
            for f,(repo,state) in enumerate(seen):
                old=(OLD/state["fixture"]).read_bytes();other=altered(old,"replace",state["lo"]+3)
                for mode in ("replace_restore","atomic_restore"):
                    names=("native","ctime_id");p=root/f"burst_{f}_{mode}.py";p.write_bytes(old)
                    visible={}
                    for arm in names:visible[arm]=decode(call(arm,p,"original","burst|"+p.name,b"",0),b"")
                    stamp=snapshot(p);prev=old
                    for j in range(32):
                        truth=other if j%2==0 else old;beforestamp=snapshot(p);writer.apply(p,mode,truth);current=snapshot(p)
                        # Run validator first, so a native read cannot artificially advance the filesystem's write timestamp.
                        for arm in ("ctime_id","native"):
                            hit=arm=="ctime_id" and stamp==current
                            result=marker(visible[arm]) if hit else call(arm,p,"repeat","burst|"+p.name+"|"+str(j),visible[arm],j)
                            visible[arm]=decode(result,visible[arm])
                            if arm=="ctime_id" and not hit:stamp=current
                            stress.append(dict(repo=repo,mode=mode,i=j,arm=arm,hit=hit,
                                source_change=prev!=truth,visible_sha=h(visible[arm]),truth_sha=h(truth),ctime_collision=beforestamp==current,
                                old_stamp=beforestamp,now_stamp=current))
                        prev=truth
        writer.close()
        for c in sessions.values():c.close()
        out=D/fs;out.mkdir(exist_ok=True)
        if tracing:
            # Trace only our two native local servers, filter to paths they actually opened under the private root.
            for arm in ("native","ctime_id"):
                raw=(root/(arm+".strace")).read_text(errors="replace")
                selected=[s for s in raw.splitlines() if re.search(r"case_\d{3}\.py",s)]
                gz(out/(arm+"_file_syscalls.json.gz"),selected)
            gz(out/"trace_receipts.json.gz",[b for b in bills if b["arm"] in ("native","ctime_id")])
            gz(out/"trace_scores.json.gz",[r for r in scores if r["arm"] in ("native","ctime_id")])
        else:
            gz(out/"native_calls.json.gz",bills);gz(out/"metrics.json.gz",scores);gz(out/"stress.json.gz",stress)
            (out/"host.json").write_text(json.dumps({"filesystem_stat":actual,"mount_parent":mount,"kernel":platform.release(),"python":platform.python_version(),"native_exe":h(exe.read_bytes()),"distro":Path("/etc/os-release").read_text()}))
        print(fs,"traced" if tracing else "timed",len(scores),len(bills),len(stress),flush=True)

if __name__=="__main__":
    assert h((OLD/"MANIFEST_SHA256.json").read_bytes())=="0c411ba80b4157db16fadbd705c08dd9807013cc683bac982140437ed7ba4722"
    for fs,m in [("ext4","/tmp"),("tmpfs","/dev/shm")]:run(fs,m,"--trace" in sys.argv)
