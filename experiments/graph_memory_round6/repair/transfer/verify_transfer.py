"""Verify original archives, restored test trees, prompt identity and trial records."""
import collections,gzip,hashlib,json,tarfile
from pathlib import Path
from driver import D,check,read,lock,sha
from grade import paths


def main():
    for name in ('policy_lock.json','packet_lock.json','gpu_answer_lock.json'):check(name)
    ids=read(D/'cohort.json')['ids']
    assert len(set(ids))==30 and not set(ids)&set(read(D.parent/'cohort.json')['ids'])
    facts=collections.Counter()
    for i in ids:
        d=D/'tasks'/i;ready=read(d/'ready.json')
        assert sha(d/'checkout.tar.gz')==ready['sha256']
        facts['verified_archives']+=1
        pack=json.loads(gzip.decompress((d/'packets.json.gz').read_bytes()))
        for a,p in pack['tokens'].items():assert p<=1800
        if i not in ids[:12]:continue
        metadata=read(d/'grading.json')
        guarded=paths(metadata['patch'])|paths(metadata['test_patch'])|set(pack['paths'])
        seen=set()
        with tarfile.open(d/'checkout.tar.gz','r:gz') as tar:
            for f in tar:
                p=f.name.partition('/')[2]
                if f.isfile() and p in guarded:
                    seen.add(p)
                    assert tar.extractfile(f).read()==(d/'base'/p).read_bytes(),(i,p)
        assert all(not(d/'base'/p).exists() for p in guarded-seen)
        facts['restored_paths']+=len(guarded)
        facts['verified_solver_tasks']+=1
        gold=read(d/'grades_v2/control.json')['gold']['gold_lines']
        cpurow=next(r for r in read(D/'cpu_rows.json') if r['id']==i)
        assert {tuple(v) for v in cpurow['sites']}=={(p,n) for p,ns in gold.items() for n in ns}
        facts['matched_independent_gold_coordinates']+=len(cpurow['sites'])
    files=[D/f for f in ('cpu_results.json','cpu_rows.json','gpu_results.json','gpu_rows.json','diagnosis.json','gpu_answer_lock.json','flat_verification.json')]
    for i in ids[:12]:
        d=D/'tasks'/i/'grades_v2'
        files.extend(sorted(d.glob('*')))
    lock('evaluation_lock.json',files,checks=facts)
    print(facts)


if __name__=='__main__':main()
