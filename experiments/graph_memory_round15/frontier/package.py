"""Produce a strict, flat transfer manifest. Refuse unknown or missing files."""
import hashlib,json
from pathlib import Path
D=Path(__file__).resolve().parent
NAMES=set("""PROTOCOL_RU.md POSTHOC_RU.md REPORT_RU.md TABLES_RU.md REPRODUCE_RU.md frontier.py freeze.py score.py labels.py tables.py write_effect.py verify.py package.py frontier_inputs.json.gz forecasts.json.gz causal_receipts.json.gz flow.json forecast.lock.json outcomes.json.gz official_patch_paths.json.gz outcome.lock.json results.json paired.json evaluation_rows.json.gz memory_cost.json write_effect.json rosters.json.gz verification.json""".split())
def main():
    others={p.name for p in D.iterdir() if p.is_file() and p.name!='MANIFEST_SHA256.json'}
    assert others==NAMES,(sorted(others-NAMES),sorted(NAMES-others))
    m={n:hashlib.sha256((D/n).read_bytes()).hexdigest() for n in sorted(others)}
    (D/'MANIFEST_SHA256.json').write_text(json.dumps(m,indent=2),encoding='utf8')
    print(len(m),'members',sum((D/n).stat().st_size for n in m),'bytes')
if __name__=='__main__':main()
