"""Create read-only-by-convention clean exports separately from evaluator data."""
from screen import *
import shutil
def tree(r,out):
    if out.exists():raise RuntimeError(f"Refusing to overlay existing checkout {out}")
    out.mkdir(parents=True)
    with tarfile.open(CACHE/(r['instance_id']+'.tar.gz')) as f:
        for m in f.getmembers():
            if not m.isfile():continue
            rel=Path(*Path(m.name).parts[1:])
            assert rel.parts and not rel.is_absolute() and '..' not in rel.parts
            p=out/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(f.extractfile(m).read())
def main():
    selected=json.loads((D/'screen.json').read_text())['selected']; by={r['instance_id']:r for r in rows()}
    for s in selected:
        r=by[s['instance']];blind=D/'blind'/s['instance'];ev=D/'evaluator'/s['instance']
        tree(r,blind/'repo');(blind/'statement.txt').write_bytes(r['problem_statement'].encode('utf8'));ev.mkdir(parents=True,exist_ok=True)
        for f in ('patch','test_patch'):(ev/(f+'.diff')).write_bytes(r[f].encode())
        save(ev/'case.json',{k:r[k] for k in ('instance_id','repo','base_commit','license','image_name','install_config','FAIL_TO_PASS','PASS_TO_PASS')})
if __name__=='__main__':main()