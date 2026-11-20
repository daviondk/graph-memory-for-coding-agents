"""Strict standalone, portable research manifest."""
import hashlib
import json
from pathlib import Path
D=Path(__file__).resolve().parent
NAMES={
  'PROTOCOL_RU.md','DIAGNOSTICS_PLAN.md','LATENCY_PLAN.md','REPORT_RU.md','REPRODUCE_RU.md','TABLES_RU.md',
  'forecast.py','grade.py','diagnostics.py','tables.py','latency.py','verify.py','package.py','capture_ties.py',
  'tie_order.json.gz','input.lock.json','predictions.json.gz','forecast.lock.json','evaluation.lock.json','inference.json',
  'evaluation_rows.json.gz','results.json','paired.json','diagnostics.json','latency.json','verification.json'
}
def main():
    found={p.name for p in D.iterdir() if p.is_file() and p.name!='MANIFEST_SHA256.json'}
    assert found==NAMES,(sorted(found-NAMES),sorted(NAMES-found))
    files={n:hashlib.sha256((D/n).read_bytes()).hexdigest() for n in sorted(found)}
    (D/'MANIFEST_SHA256.json').write_text(json.dumps(files,indent=2,sort_keys=True),encoding='utf8')
    print(f'{len(files)} members, {sum((D/n).stat().st_size for n in files)} bytes')
if __name__=='__main__':main()
