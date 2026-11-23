"""Reparse the native raw subprocess output and compare the export against published test lists."""
import importlib.util,json
from pathlib import Path
V=Path("D:/CodexResearch/x20-official-vibe/VibeMemBench/scripts/vendor/eval.py")
module=importlib.util.spec_from_file_location("vibe_public_holdout",V)
official=importlib.util.module_from_spec(module);module.loader.exec_module(official)
def check(item,spec,unit):
    cfg=spec["install_config"]
    if isinstance(cfg,str):cfg=json.loads(cfg)
    raw=unit.read_text(encoding="utf8");parse=official.get_parser(cfg["log_parser"])
    normalize=official._normalize_test_name
    status={normalize(name):value for name,value in parse(raw).items()}
    actual={key for key,val in status.items() if val=="PASSED"}
    f2p=set(map(normalize,spec["FAIL_TO_PASS"]));p2p=set(map(normalize,spec["PASS_TO_PASS"]))
    assert {normalize(x) for x in item["from_fail_to_pass"]}==f2p&actual
    assert {normalize(x) for x in item["failed_from_pass_to_pass"]}==p2p-actual
    assert item["passed_match"]==(f2p|p2p==actual)
    return dict(f2p_passed=len(f2p&actual),p2p_passed=len(p2p&actual),lost_p2p=len(p2p-actual),test_expected=len(f2p|p2p),raw_passed_count=len(actual))
