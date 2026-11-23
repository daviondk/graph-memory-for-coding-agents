"""Run the preregistered earlier commit interval using exactly the primary study's selection and runners."""
import json
import shutil
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
PRIMARY=ROOT.parent/"receipt_invalidation"
sys.path.insert(0,str(PRIMARY))
import observe, rollback, testmon_comparison, execute_graph

def run():
    phase=sys.argv[1]
    for module in (observe,rollback,testmon_comparison,execute_graph):
        module.ROOT=ROOT
    cache=Path("D:/CodexResearch/x20-round17-test-holdout")
    for module in (rollback,testmon_comparison,execute_graph):
        module.CACHE=cache
    rollback.VERSIONS=("v10.2.0","v10.5.0")
    if phase=="prepare":
        scripts=("runner.py","rollback.py","ROLLBACK_PROTOCOL_RU.md","testmon_comparison.py","TESTMON_PROTOCOL_RU.md","trace_plugin.py","execute_graph.py","GRAPH_ACTION_PROTOCOL_RU.md")
        for name in scripts:shutil.copyfile(PRIMARY/name,ROOT/name)
        trace=rollback.read(PRIMARY/"rollback-roster.json")["blocks"]
        source={s[r] for s in trace for r in ("commit","parent")}
        before={n:rollback.sha((ROOT/n).read_bytes()) for n in (*scripts,"PROTOCOL_RU.md","run_holdout.py")}
        rollback.put("replication-lock.json",{"original":str(PRIMARY),"source_hashes":before,"exclude_commit_parent":sorted(source)})
        rollback.prepare()
        holdout=rollback.read(ROOT/"rollback-roster.json")["blocks"]
        assert not {b[r] for b in holdout for r in ("commit","parent")} & source
        return
    lock=rollback.read(ROOT/"replication-lock.json")["source_hashes"]
    for n,expected in lock.items():assert rollback.sha((ROOT/n).read_bytes())==expected
    if not rollback.read(ROOT/"rollback-roster.json")["blocks"]:
        print("No eligible commits");return
    if phase=="reference":rollback.main()
    elif phase=="native":testmon_comparison.main()
    elif phase=="action":execute_graph.main()
    else:raise ValueError(phase)
if __name__=="__main__":run()
