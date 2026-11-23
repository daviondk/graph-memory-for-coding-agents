"""Freeze pytest's actual nodeids before comparison and retain uncollected AST method names without replacement."""
import json
import os
import subprocess
import tempfile
from pathlib import Path
from run_holdout import PRIMARY, ROOT
import rollback
from testmon_comparison import PY,as_node

def main():
    read=rollback.read
    roster=read(ROOT/"rollback-roster.json")
    if (ROOT/"collection-audit.json").exists():
        assert rollback.sha((ROOT/"rollback-roster.json").read_bytes())==read(ROOT/"collection-audit.json")["updated_hash"]
        return
    original=(ROOT/"rollback-roster.json").read_bytes()
    (ROOT/"rollback-roster-original.json").write_bytes(original)
    excluded=[];audit=[]
    cache=Path("D:/CodexResearch/x20-round17-test-holdout");cache.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache) as t:
        for b in roster["blocks"]:
            cwd=Path(t)/b["commit"]
            rollback.build(b,cwd)
            cmd=[str(PY),"-B","-m","pytest","--collect-only","-q","-o","addopts=","tests"]
            r=subprocess.run(cmd,cwd=cwd,env={**os.environ,"PYTEST_DISABLE_PLUGIN_AUTOLOAD":"1","PYTHONUTF8":"1","PYTHONDONTWRITEBYTECODE":"1"},capture_output=True)
            log=r.stdout.decode()+r.stderr.decode()
            assert r.returncode==0,log[-1700:]
            seen={v.strip().replace("\\","/") for v in log.splitlines() if "::" in v}
            before=b["tests"];b["tests"]=[v for v in before if as_node(v["name"]) in seen]
            excluded.extend({"commit":b["commit"],"uncollected":v["name"]} for v in before if v not in b["tests"])
            audit.append({"commit":b["commit"],"before":len(before),"after":len(b["tests"]),"collected":len(seen),"native_listing_sha":rollback.sha(log.encode())})
    before_lock=read(ROOT/"rollback-lock.json")
    assert before_lock["rollback-roster.json"]==rollback.sha(original)
    def save(n,obj):(ROOT/n).write_bytes(json.dumps(obj,sort_keys=True,separators=(",",":")).encode())
    save("rollback-roster.json",roster)
    after=rollback.sha((ROOT/"rollback-roster.json").read_bytes())
    save("collection-audit.json",{"earlier_lock":before_lock,"updated_hash":after,"files":audit,"exclusions":excluded,"reason":"AST collector included methods declared on standalone mixin classes, which are not unittest.TestCase and have no pytest nodeid at that address. First unittest loading stopped before scoring intervention. Native collect-only confirms original node population. No replacements or post-change outcome selection."})
    save("rollback-lock.json",{**before_lock,"rollback-roster.json":after})
    print("uncollected",len(excluded),[(x["before"],x["after"]) for x in audit])
if __name__=="__main__":main()
