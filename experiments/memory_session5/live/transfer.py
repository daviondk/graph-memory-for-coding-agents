from common import *
import common,infer,prepare
def main():
    root=ROOT/'transfer';root.mkdir(exist_ok=True)
    roster=read('roster.json');denied=set(roster['excluded'])
    ids=sorted(set(corpus())-denied,key=lambda i:digest('qwen-boundary-5|'+i))[48:]
    assert set(ids).isdisjoint(roster['ids']) and len(ids)==63
    save('transfer/roster.json',{'ids':ids,'source':'original source-only hash roster positions 49 onwards'})
    # infer imports scalar ROOT once. Files for each executable branch use the separate transfer root.
    # Source assets and implementation stay shared: pin their parent-relative paths.
    paths=list(read('design_lock.json'))
    hashes={'../'+f:digest((ROOT/f).read_bytes()) for f in paths}
    hashes['../TRANSFER_PRELOCK.md']=digest((ROOT/'TRANSFER_PRELOCK.md').read_bytes())
    hashes['../transfer.py']=digest((ROOT/'transfer.py').read_bytes())
    hashes['roster.json']=digest((root/'roster.json').read_bytes())
    save('transfer/design_lock.json',hashes)
    rs=corpus()
    for i in ids:
        path=root/'work'/slug(i)/'solution.py';path.parent.mkdir(exist_ok=True,parents=True);path.write_text(src(rs[i]),encoding='utf8')
    # Database and evaluator are immutable and replicated for portable isolated verification.
    import shutil
    for f in ('dataset.jsonl','worker.py'):shutil.copyfile(ROOT/f,root/f)
    import time
    while not (ROOT/'prediction_lock.json').exists():time.sleep(2)
    common.ROOT=root;infer.ROOT=root
    infer.main()
if __name__=='__main__':main()
