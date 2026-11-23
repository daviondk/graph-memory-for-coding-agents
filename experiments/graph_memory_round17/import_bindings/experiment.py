"""Causal microbenchmark for test validity after changing an import-time producer."""
import ast
import collections
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CACHE = Path("D:/CodexResearch/x20-r17-import-binding-runs")
PY = Path("D:/CodexResearch/x20-validity-releases/testmon-env/Scripts/python.exe")
KINDS = ("direct","global","chain","mapping","default","class","register","dynamic","unused")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(name, data):
    raw = json.dumps(data,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()
    (ROOT/name).write_bytes(gzip.compress(raw,mtime=0) if name.endswith(".gz") else raw)


def run(cwd, label, *args, trace=False, testmon=False):
    outfile = cwd/(label+".json")
    custom = ["-p","testmon.pytest_testmon","--testmon"] if testmon else []
    cmd = [str(PY),"-m","pytest","-q","-p","observe_binding",*custom, *args]
    env = dict(os.environ, PYTHONPATH=str(ROOT)+os.pathsep+str(cwd),
               PYTHONDONTWRITEBYTECODE="1",PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
               PYTHONUTF8="1",BIND_TRACE=str(int(trace)),BIND_OUT=str(outfile))
    start = time.perf_counter()
    result = subprocess.run(cmd,cwd=cwd,env=env,capture_output=True,timeout=60)
    elapsed = time.perf_counter()-start
    assert outfile.exists() and result.returncode in (0,1,5), result.stderr.decode()[-2000:]
    return {"rc":result.returncode,"seconds":elapsed,"output":result.stdout.decode(),
            "error":result.stderr.decode(),"native":json.loads(outfile.read_bytes())}


def setup(directory, source):
    directory.mkdir(parents=True,exist_ok=False)
    (directory/"example_library.py").write_bytes(source)
    shutil.copyfile(ROOT/"example_tests.py",directory/"test_features.py")


def provenance(text, receipt):
    module = ast.parse(text)
    bindings = collections.defaultdict(set)
    opaque = set()
    observed = set()
    for stmt in module.body:
        calls = {c for line, names in receipt["import_calls"].items()
                 if stmt.lineno <= int(line) <= stmt.end_lineno for c in names}
        observed |= calls
        if isinstance(stmt, ast.Assign) and all(isinstance(t,ast.Name) for t in stmt.targets):
            reads = {n.id for n in ast.walk(stmt.value) if isinstance(n,ast.Name)}
            names = [t.id for t in stmt.targets]
        elif isinstance(stmt, (ast.FunctionDef,ast.ClassDef)):
            # Calls made while defining a function/class can bind its defaults or fields.
            nodes = list(stmt.decorator_list)
            if isinstance(stmt, ast.FunctionDef):
                nodes.extend(stmt.args.defaults)
                nodes.extend(n for n in stmt.args.kw_defaults if n is not None)
            else:
                nodes.extend(stmt.bases)
                nodes.extend(stmt.keywords)
            reads = {n.id for expr in nodes for n in ast.walk(expr) if isinstance(n,ast.Name)}
            names = [stmt.name]
        else:
            opaque |= calls
            continue
        ancestors = set(calls)
        for read in reads:
            ancestors |= bindings.get(read,set())
        for name in names:
            bindings[name] = ancestors.copy()
    return bindings, opaque, observed


def positive(status):
    return all(status.get(phase)=="passed" for phase in ("setup","call","teardown"))


def main():
    CACHE.mkdir(parents=True,exist_ok=True)
    first = ROOT/"example_library.py"
    source = first.read_bytes()
    identity = sha(source+(ROOT/"experiment.py").read_bytes())[:16]
    run_root = CACHE/identity
    assert not run_root.exists(), "To reproduce, use a new scratch root."
    run_root.mkdir()
    baseline = run_root/"baseline"
    setup(baseline,source)
    warm = run(baseline,"observed","test_features.py",trace=True)
    obs = warm["native"]
    assert len(obs["outcomes"])==10 and all(map(positive,obs["outcomes"].values()))
    binds, opaque, import_executed = provenance(source,obs)
    plan = {}
    for kind in KINDS:
        change = kind+"_source"
        arms = {"all":sorted(obs["tests"]),"function":[],"import_file":[],"bindings":[]}
        for node,metadata in obs["tests"].items():
            deps = set(metadata["functions"])
            names = set(metadata["names"]) | deps
            if change in deps:
                arms["function"].append(node)
            if change in deps or change in import_executed:
                arms["import_file"].append(node)
            needs = change in deps or change in opaque or bool(names & {"globals","locals"})
            for name in names:
                needs |= change in binds.get(name,set())
            if needs:
                arms["bindings"].append(node)
        plan[kind] = {k:sorted(v) for k,v in arms.items()}
    save("warm-observation.gz",warm)
    save("import-graph.json",dict(bindings={k:sorted(v) for k,v in binds.items()},opaque=sorted(opaque),
                                  import_executed=sorted(import_executed)))
    save("forecasts.json",plan)
    save("forecast-seal.json",{f:sha((ROOT/f).read_bytes()) for f in (
        "forecasts.json","warm-observation.gz","import-graph.json","experiment.py",
        "observe_binding.py","example_library.py","example_tests.py","PROTOCOL_RU.md")})
    all_runs = {}
    scores = collections.defaultdict(collections.Counter)
    for kind in KINDS:
        mutation = ("def "+kind+"_source():\n    return 2").encode()
        assert source.count(mutation)==1
        changed = source.replace(mutation,mutation[:-1]+b"3")
        cwd=run_root/kind
        setup(cwd,source)
        warm_mon=run(cwd,"mon-pre","test_features.py",testmon=True)
        unchanged=run(cwd,"mon-stable","test_features.py",testmon=True)
        assert all(map(positive,warm_mon["native"]["outcomes"].values())) and len(warm_mon["native"]["outcomes"])==10
        assert not unchanged["native"]["outcomes"], (kind,unchanged)
        (cwd/"example_library.py").write_bytes(changed)
        native=run(cwd,"mon-changed","test_features.py",testmon=True)
        full=run(cwd,"oracle","test_features.py")
        assert set(full["native"]["outcomes"])==set(obs["outcomes"])
        actual={k for k,v in full["native"]["outcomes"].items() if not positive(v)}
        arms=dict(plan[kind],testmon=sorted(native["native"]["outcomes"]))
        picked=arms["bindings"]
        # The graph-selected checks are run in an ordinary fresh pytest process.
        execution=run(cwd,"selected",*picked) if picked else {}
        assert not picked or set(execution["native"]["outcomes"])==set(picked)
        for label, nodes in arms.items():
            checked=set(nodes)
            scores[label].update({"rerun":len(checked),"reuse":10-len(checked),"caught":len(checked&actual),
                                  "false_reuse":len(actual-checked),"total_regressions":len(actual)})
        all_runs[kind]=dict(changed_sha=sha(changed),failed=sorted(actual),arms=arms,
                            warm=warm_mon,unchanged=unchanged,testmon=native,full=full,selected=execution)
        save("runs.gz",all_runs)
    save("results.json",dict(arms=scores,cases={k:{"failed":r["failed"],"reruns":{a:len(ns) for a,ns in r["arms"].items()}}
                                               for k,r in all_runs.items()}))
    print(dict(scores))


if __name__ == "__main__":
    main()

