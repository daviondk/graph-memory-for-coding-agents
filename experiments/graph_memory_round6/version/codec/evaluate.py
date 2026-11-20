"""Resolve the intended frozen task-cluster evaluator by explicit filesystem path."""
import importlib.util
import json
from pathlib import Path
import score_codec
import replay

if __name__=='__main__':
    root=Path(__file__).resolve().parent
    seal=json.loads((root/'evaluator_lock.json').read_bytes())
    for path,h in seal['files'].items(): assert replay.digest(root/path)==h
    spec=importlib.util.spec_from_file_location('r6_version_evaluator',root.parent/'score.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    score_codec.grade=module
    score_codec.main()
