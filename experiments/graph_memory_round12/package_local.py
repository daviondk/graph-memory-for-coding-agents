"""Audit, build, verify or export the R12 research archive. No Git operations."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent
DEFAULT = Path("D:/CodexResearch/x20-bench-workspace/outputs/graph-memory-round12-records.zip")
MANIFEST = "MANIFEST.sha256"
SEALED = ("dynamic_graph", "negative_external")
STUDIES = {*SEALED, "dreambench", "predicate", "subsumption", "vibe"}
IDS = ("adamchainz__flake8-comprehensions-553", "mpmath__mpmath-881")
ARMS = ("base", "raw", "graph")
GRADES = ("gold", "marker")
PERMITTED_PARQUET = "0be6108859149979d60da8ad3507f46cc308b34f10fe186826f1eb6e09c5b884"
UPSTREAM = Path("D:/CodexResearch/x20-official-vibe/VibeMemBench")
UPSTREAM_FILES = ("LICENSE", "scripts/vendor/eval.py", "scripts/vendor/log_parsers.py", "scripts/run_eval.py")
SMALL_EXT = {".json", ".jsonl", ".md", ".py", ".ps1", ".txt", ".gz", ".log", ".tex", ".csv", ".tsv", ".yaml", ".yml", ".sh"}
EXCLUDE_DIR = {".git", "__pycache__", "vendor", "downloads", "pytest-deps", "upstream", "successor-public", "worktree", "worktrees", "checkouts", "venv", "node_modules", "weights", "models-cache", "scratch", "cache", "tmp", "secrets"}
BAD_WIN = {"con", "aux", "nul", "prn", *(f"com{i}" for i in range(1,10)), *(f"lpt{i}" for i in range(1,10))}
HEX = re.compile(r"^[0-9a-f]{64}$")
VIBE_RUN = {"launch.json", "order.json", "cohort.json", "proxy-launch.json", "assignment-lock.json", "requests.jsonl", "run-all.log", "prepare-final.log", "prepare.log", "pull-ready0.log", "pull-ready1.log", "pull0.log", "pull1.log", "memory.py", "run.py", "seed_proxy.py", "start_server.ps1", "PROTOCOL_RU.md", "PREFLIGHT.md"}
G_TOP = {"environment.json", "results.json", "activity.log", "grade.py", "audit.py", "report.py", "bridge.py", "environment.py", "README_RU.md", "REPORT_RU.md"}
G_OUTPUT = {"result.json", "native-report.json", "eval_stdout.log", "eval_stderr.log", "container.log", "unit.log"}
E_OUTPUT = {"container_id.txt", "finished.json", "result.json", "retrieved_experiences.txt", "_experience_override.yaml", "run.log"}

def linked(path):
    mode = path.lstat()
    return stat.S_ISLNK(mode.st_mode) or bool(getattr(mode, "st_file_attributes", 0)&1024)

def portable(name):
    p = PurePosixPath(name)
    return bool(name and p.as_posix()==name and not p.is_absolute() and not re.search(r'[\\:<>"|?*]', name)
                and all(part not in {".",".."} and not any(ord(c)<32 for c in part)
                        and not part.endswith((" ",".")) and part.split(".")[0].casefold() not in BAD_WIN for part in p.parts))

def accepted(name):
    if not portable(name): return False
    p = PurePosixPath(name); parts = p.parts
    if len(parts)==1: return p.name=="package_local.py" or p.suffix==".md"
    root, *rest = parts
    if root not in STUDIES: return False
    if root=="vibe" and rest[0]=="official_source":
        return "/".join(rest[1:]) in UPSTREAM_FILES
    if any(s.startswith(".") or s.casefold() in EXCLUDE_DIR or s.casefold().endswith(".git") for s in rest): return False
    if root=="dynamic_graph":
        return p.suffix in {".json",".gz",".py",".log",".md"} or (p.suffix==".bin" and rest[:-1] in (["archive"],["wide","archive"]))
    if root=="negative_external": return p.suffix in {".json",".gz",".py",".md"}
    if root=="dreambench": return len(rest)==1 and p.suffix in SMALL_EXT
    if root=="predicate": return len(rest)==1 and p.suffix in SMALL_EXT
    if root=="subsumption": return (len(rest)==1 or (len(rest)==2 and rest[0]=="replication")) and p.suffix in SMALL_EXT
    if len(rest)==1:
        return p.name in VIBE_RUN or p.suffix in {".py",".md"} or p.name in {"results.json","verification.json","delivery-lock.json","calls.json.gz","trajectories.json.gz"}
    if rest==["subset","test.parquet"]:return True
    if rest[0]=="preflight-before-path-fix":
        rest=rest[1:]
        if len(rest)==1:return rest[0] in {"memory.py","assignment-lock.json"}
    if rest[0]=="memories":
        return len(rest)==5 and rest[1] in {"raw","graph"} and rest[2]=="python" and rest[3] in IDS and rest[4] in {"memory.txt","memory.json"}
    if rest[0]=="episodes":
        return len(rest)==6 and rest[1]=="python" and rest[2] in IDS and rest[3] in ARMS and rest[4]=="seed0" and (rest[5] in E_OUTPUT or rest[5]==rest[2]+".traj.json")
    if rest[0]=="grading":
        if len(rest)==2:return rest[1] in G_TOP
        if rest==["grading","bin","docker"]:return True
        return len(rest)==5 and rest[2] in IDS and rest[4] in G_OUTPUT and ((rest[1]=="models" and rest[3] in ARMS) or (rest[1]=="controls" and rest[3] in GRADES))
    return False

def safe_file(base,name):
    if not portable(name):raise ValueError(f"Unsafe path {name}")
    path=base
    for part in PurePosixPath(name).parts:
        path=path/part
        if linked(path):raise ValueError(f"Linked input path: {path}")
    if not path.is_file():raise ValueError(f"Expected regular file: {path}")
    return path

def sha(raw):return hashlib.sha256(raw).hexdigest()
def file_hash(path):
    with path.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def inventory():
    items={}
    def add(key,path):
        if key in items:raise ValueError(f"Duplicate selection: {key}")
        if not accepted(key):raise ValueError(f"File type/path outside policy: {key}")
        items[key]=path
    for study in SEALED:
        name=study+"/MANIFEST_SHA256.json";p=safe_file(ROOT,name);add(name,p)
        manifest=json.loads(p.read_bytes())
        for rel,h in manifest.items():
            if not HEX.fullmatch(h) or not portable(rel):raise ValueError(f"Invalid inner manifest: {rel}")
            add(study+"/"+rel,safe_file(ROOT,study+"/"+rel))
    for base,dirs,files in os.walk(ROOT,topdown=True,followlinks=False):
        parent=Path(base); rel=parent.relative_to(ROOT); level=rel.parts
        if not level:dirs[:]=sorted(x for x in dirs if x in STUDIES- set(SEALED) and not linked(parent/x))
        elif level[0]=="dreambench" or level[0]=="predicate":dirs[:]=[]
        elif level[0]=="subsumption":dirs[:]=[x for x in dirs if level==("subsumption",) and x=="replication" and not linked(parent/x)]
        elif level[0]=="vibe":
            dirs[:]=sorted(x for x in dirs if x not in EXCLUDE_DIR and not x.startswith(".") and not linked(parent/x)
                           and (len(level)>1 or x in {"memories","grading","preflight-before-path-fix","episodes","subset"})
                           and not (level==("vibe","grading") and x not in {"controls","models","bin"}))
        for f in files:
            p=parent/f;key=p.relative_to(ROOT).as_posix()
            if accepted(key):add(key,safe_file(ROOT,key))
    for relative in UPSTREAM_FILES:
        key="vibe/official_source/"+relative
        if (ROOT/key).is_file():source=safe_file(ROOT,key)
        else:source=safe_file(UPSTREAM,relative)
        add(key,source)
    if len(items)!=len({n.casefold() for n in items}):raise ValueError("Case-insensitive name collision")
    return dict(sorted(items.items()))


def evidence(names,read,digests):
    """Validate the same semantic evidence on disk and in a portable archive."""
    names=set(names); pending=[]; stats={}
    def doc(key):return json.loads(read(key))
    def need(key):
        if key not in names:
            pending.append(key)
            return False
        return True
    def require_hash(key,expected):
        if not isinstance(expected,str) or not HEX.fullmatch(expected) or digests.get(key)!=expected:
            raise ValueError(f"Record digest does not match study receipt: {key}")
    def locked(base,rel):
        lock=base+'/'+rel
        if need(lock):
            d=doc(lock)
            table=d.get("files",d)
            for key,value in table.items():require_hash(base+'/'+key,value)
            return len(table)
        return 0
    for study in SEALED:
        prefix=study+'/';indexed=doc(prefix+'MANIFEST_SHA256.json')
        if {k for k in names if k.startswith(prefix)}!={prefix+'MANIFEST_SHA256.json',*(prefix+k for k in indexed)}:
            raise ValueError(f"{study} entry set differs from its study manifest")
        for child,h in indexed.items():require_hash(prefix+child,h)
        stats[study+'_hashed']=len(indexed)
    stats['dreambench_release_records']=locked('dreambench','delivery-lock.json')
    locked('dreambench','plan-lock.json')
    for part in ['dreambench/verification.json','dreambench/release-verification.json','dreambench/results.json','predicate/results.json','predicate/rows.gz','subsumption/decisions.gz','subsumption/results.json','subsumption/replication/results.json']:
        need(part)
    locked('subsumption','lock.json');locked('subsumption/replication','lock.json')
    for part in ['REPORT_RU.md','REPRODUCE_RU.md','vibe/cohort.json','vibe/order.json','vibe/requests.jsonl','vibe/grading/environment.json','vibe/grading/REPORT_RU.md','vibe/grading/README_RU.md']:
        need(part)
    dataset='vibe/subset/test.parquet'
    require_hash(dataset,PERMITTED_PARQUET)
    stats['solver_subset']={'rows':2,'sha256':PERMITTED_PARQUET,'fields':['instance_id','repo','language','problem_statement','image_name','base_commit']}
    prec='vibe/preflight-before-path-fix/'
    if need('vibe/assignment-lock.json') and need(prec+'assignment-lock.json'):
        live=doc('vibe/assignment-lock.json');old=doc(prec+'assignment-lock.json');stable=[];different=[]
        if set(live)!=set(old):raise ValueError("Preflight/final assignment record set differs")
        for key,digest in live.items():
            require_hash('vibe/'+key,digest)
            historical=prec+key if prec+key in names else 'vibe/'+key
            require_hash(historical,old[key])
            (stable if old[key]==digest else different).append(key)
        stats['preflight']={'identical_locked_records':stable,'changed_locked_records':different}
    expected_runs={(iid,m) for iid in IDS for m in ARMS};expected_controls={(iid,m) for iid in IDS for m in GRADES}
    if 'vibe/cohort.json' in names:
        if {v['instance_id'] for v in doc('vibe/cohort.json')['targets']}!=set(IDS):raise ValueError("Unexpected solver cohort")
    if 'vibe/order.json' in names:
        order=doc('vibe/order.json')
        if len(order)!=len(expected_runs) or {tuple(row) for row in order}!=expected_runs:raise ValueError("Unexpected scheduled episodes")
    closed=[];graded=[];controlled=[]
    def safe_trajectory(data):
        # The local OpenAI-compatible server uses a dummy key. Do not archive a real credential.
        stack=[data]
        while stack:
            value=stack.pop()
            if isinstance(value,dict):
                for k,v in value.items():
                    if k.lower() in {'api_key','access_token','refresh_token','authorization'} and v not in ('','local','dummy','EMPTY','empty','none','not-needed','not-a-real-key','sk-local','no-key','local-only',None):
                        raise ValueError("Unexpected credential material in trajectory")
                    stack.append(v)
            elif isinstance(value,list):stack.extend(value)
    for iid,method in sorted(expected_runs | expected_controls):
        is_model=(iid,method) in expected_runs
        if is_model:
            prefix=f'vibe/episodes/python/{iid}/{method}/seed0/'
            finished=prefix+'finished.json';traj=prefix+iid+'.traj.json'
            if need(finished):
                receipt=doc(finished)
                if (receipt['instance_id'],receipt['method'],receipt['seed'],receipt['status'],receipt['returncode'])!=(iid,method,0,'ok',0):
                    raise ValueError(f"Solver finish receipt differs: {iid}/{method}")
                if need(traj):
                    safe_trajectory(doc(traj));closed.append((iid,method))
                if need(prefix+'result.json') and doc(prefix+'result.json')!=receipt:raise ValueError(f"Solver finish/result mismatch: {iid}/{method}")
                if method!='base':
                    card=prefix+'retrieved_experiences.txt'
                    if need(card):
                        # The vendor may wrap the prepared card; both pieces remain available.
                        source=f'vibe/memories/{method}/python/{iid}/memory.txt'
                        designated=read(source).decode('utf8').strip()
                        actual=read(card).decode('utf8').strip()
                        if not designated or designated not in actual:raise ValueError(f"Solver-delivered card differs: {iid}/{method}")
        prefix=f"vibe/grading/{'models' if is_model else 'controls'}/{iid}/{method}/"
        if need(prefix+'result.json'):
            row=doc(prefix+'result.json')
            if (row.get('instance'),row.get('method'))!=(iid,method):raise ValueError(f"Wrong grade identity: {iid}/{method}")
            for k,h in row['hashes'].items():require_hash(prefix+k,h)
            for f in ['native-report.json','eval_stdout.log','eval_stderr.log']:need(prefix+f)
            if row['unit_exit'] is not None:
                need(prefix+'unit.log');need(prefix+'container.log')
            if is_model:
                require_hash(f'vibe/episodes/python/{iid}/{method}/seed0/finished.json',row['finish_sha'])
                graded.append((iid,method))
            else:controlled.append((iid,method))
    stats['solver_finished']=len(closed);stats['solver_grades']=len(graded);stats['official_controls']=len(controlled)
    ledger='vibe/grading/results.json'
    if need(ledger):
        r=doc(ledger);rows=r['rows']; listed=[(row['instance'],row['method']) for row in rows]
        if len(set(listed))!=len(listed) or not set(listed)<=expected_runs|expected_controls:raise ValueError("Unexpected or duplicate official grades")
        if r.get('complete') is not True or r.get('expected')!=10 or r.get('pending')!=[] or set(listed)!=expected_runs|expected_controls:
            pending.append('vibe/grading/results.json:complete=10/10')
        for path,h in r['release_files'].items():
            norm=path.replace(chr(92),'/')
            if '/VibeMemBench/scripts/' in norm:
                suffix=norm.split('/VibeMemBench/',1)[1];require_hash('vibe/official_source/'+suffix,h)
            elif '/graph_memory_round12/vibe/' in norm:
                require_hash('vibe/'+norm.split('/graph_memory_round12/vibe/',1)[1],h)
        stats['upstream_source_bundled']=len(UPSTREAM_FILES)-1
    return {'ready':not pending,'pending':pending,'evidence':stats}


def manifest_bytes(hashes):
    return "".join(f"{h}  {name}\n" for name,h in sorted(hashes.items())).encode("utf8")

def parse_manifest(raw):
    output={}
    for line in raw.decode("utf8").splitlines():
        match=re.fullmatch(r"([a-f0-9]{64})  (.+)",line)
        if not match or match[2] in output:raise ValueError("Invalid ZIP SHA-256 manifest")
        output[match[2]]=match[1]
    if manifest_bytes(output)!=raw:raise ValueError("Noncanonical manifest text")
    return output

def summarise(files,hashes):
    data=evidence(files,lambda k:files[k].read_bytes(),hashes)
    counts=Counter();sizes=Counter();large=[]
    for name,path in files.items():
        group=name.split('/',1)[0] if '/' in name else '(root)';n=path.stat().st_size
        counts[group]+=1;sizes[group]+=n;large.append((n,name))
    data.update(files=len(files),bytes=sum(sizes.values()),files_per_study=counts,bytes_per_study=sizes,
                largest=[{'path':p,'bytes':n} for n,p in sorted(large,reverse=True)[:5]],
                single_files_at_or_above_100_MiB=[p for n,p in large if n>=100*1024**2],
                excluded=['official benchmark/test.parquet','private evaluator inputs','downloaded packages, models and source trees','local server stdout/stderr and Docker daemon logs'])
    return data

def verify(archive):
    with zipfile.ZipFile(archive) as reader:
        entries=reader.infolist();names=[e.filename for e in entries]
        if names.count(MANIFEST)!=1 or len(names)!=len({n.casefold() for n in names}):raise ValueError("Missing manifest or duplicate ZIP name")
        for ent in entries:
            if not portable(ent.filename) or not stat.S_ISREG(ent.external_attr>>16) or (ent.filename!=MANIFEST and not accepted(ent.filename)):
                raise ValueError(f"Unsafe or unexpected archive entry: {ent.filename}")
        hashes=parse_manifest(reader.read(MANIFEST))
        if set(hashes)!=set(names)-{MANIFEST}:raise ValueError("Archive coverage differs from manifest")
        for name,h in hashes.items():
            with reader.open(name) as entry:
                if hashlib.file_digest(entry,'sha256').hexdigest()!=h:raise ValueError(f"Archive checksum mismatch: {name}")
        check=evidence(hashes,reader.read,hashes)
        if not check['ready']:raise ValueError("Archive incomplete: "+", ".join(check['pending']))
    return hashes

def outside(path):
    if path.resolve().is_relative_to(ROOT.resolve()):raise ValueError("Target must be outside research inputs")

def write_member(out,name,data):
    info=zipfile.ZipInfo(name,(1980,1,1,0,0,0));info.create_system=3
    info.external_attr=(stat.S_IFREG|0o644)<<16
    info.compress_type=zipfile.ZIP_STORED if name.endswith(('.gz','.parquet')) else zipfile.ZIP_DEFLATED
    with out.open(info,'w') as dest:
        if isinstance(data,bytes):dest.write(data)
        else:shutil.copyfileobj(data,dest,1024*1024)

def build(target,replace=False):
    outside(target)
    if target.exists() and not replace:raise FileExistsError(target)
    files=inventory();hashes={k:file_hash(v) for k,v in files.items()}
    audited=summarise(files,hashes)
    if not audited['ready']:raise ValueError("Final archive pending: "+", ".join(audited['pending']))
    target.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix=".round12-",suffix=".zip",dir=target.parent);os.close(fd)
    stage=Path(name)
    try:
        with zipfile.ZipFile(stage,'w') as out:
            for k,path in files.items():
                with path.open('rb') as inp:write_member(out,k,inp)
            write_member(out,MANIFEST,manifest_bytes(hashes))
        if verify(stage)!=hashes or {k:file_hash(v) for k,v in inventory().items()}!=hashes:raise RuntimeError("Source changed during snapshot")
        if replace:os.replace(stage,target)
        else:os.link(stage,target)
    finally:stage.unlink(missing_ok=True)
    return hashes

def export(archive,target):
    outside(target)
    if target.exists() or target.is_symlink():raise FileExistsError(f"Export needs a new directory: {target}")
    hashes=verify(archive);target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".round12-export-",dir=target.parent) as tmp:
        staging=Path(tmp)/"records";staging.mkdir()
        with zipfile.ZipFile(archive) as reader:
            for name in [*hashes,MANIFEST]:
                out=staging/name;out.parent.mkdir(parents=True,exist_ok=True)
                with reader.open(name) as inp, out.open('xb') as dest:shutil.copyfileobj(inp,dest,1024*1024)
        if {k:file_hash(staging/k) for k in hashes}!=hashes or (staging/MANIFEST).read_bytes()!=manifest_bytes(hashes):
            raise RuntimeError("Export integrity error")
        if target.exists() or target.is_symlink():raise FileExistsError(target)
        staging.rename(target)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    g=p.add_mutually_exclusive_group()
    g.add_argument('--audit',action='store_true',help='read-only coverage and current pending checks')
    g.add_argument('--list',action='store_true',help='print selected archive member names')
    g.add_argument('--verify',type=Path,metavar='ZIP')
    g.add_argument('--output',type=Path,metavar='ZIP')
    p.add_argument('--replace',action='store_true');p.add_argument('--export',type=Path,metavar='NEW_DIRECTORY')
    opts=p.parse_args()
    if opts.audit or opts.list:
        if opts.replace or opts.export:p.error("Read-only modes cannot export or replace")
        files=inventory()
        if opts.list:print('\n'.join(files))
        else:print(json.dumps(summarise(files,{k:file_hash(p) for k,p in files.items()}),indent=2,ensure_ascii=False))
        return
    if opts.verify and opts.replace:p.error("--verify cannot replace an archive")
    target=(opts.verify or opts.output or DEFAULT).resolve()
    records=verify(target) if opts.verify else build(target,opts.replace)
    if opts.export:export(target,opts.export.resolve())
    print(f'{len(records)} files | SHA-256 {file_hash(target)} | {target}')
if __name__=='__main__':main()

