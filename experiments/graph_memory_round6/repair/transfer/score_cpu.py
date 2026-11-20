"""Grade after commitment, using the same old-coordinate definition as parent grade.py."""
import collections,difflib,gzip,json,math,random,re,subprocess,tempfile
from pathlib import Path
from driver import D,check,read,lock
from grade import launch,paths
ARMS=('flat','address','symbol','evidence')
def gold_sites(dest):
    g=read(dest/'grading.json')['patch']
    names={s for s in re.findall(r'(?m)^(?:--- a/|\+\+\+ b/)([^\s]+)',g)}
    assert all(not Path(p).is_absolute() and '..' not in Path(p).parts for p in names)
    with tempfile.TemporaryDirectory(dir=dest) as tmp:
        root=Path(tmp)
        for p in names:
            src=dest/'base'/p
            if src.is_file():
                q=root/p;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(src.read_bytes())
        r=launch(root,g.encode(),['git','apply','--whitespace=nowarn','-'])
        assert r.returncode==0,(dest.name,r.stdout)
        sites=set()
        for p in paths(g):
            a=dest/'base'/p;b=root/p
            if not (a.is_file() and b.is_file()):continue
            before=a.read_bytes().decode().splitlines();after=b.read_bytes().decode().splitlines()
            for tag,lo,hi,_,_ in difflib.SequenceMatcher(None,before,after,autojunk=False).get_opcodes():
                if tag!='equal':sites.update((p,n) for n in range(lo+1,max(lo+1,hi)+1))
        return sites


def pair(rows,a,b,field):
    ds=[int(r['arms'][a][field])-int(r['arms'][b][field]) for r in rows]
    wins=sum(d>0 for d in ds);losses=sum(d<0 for d in ds);n=wins+losses
    rng=random.Random(67231);bs=sorted(sum(rng.choice(ds) for _ in ds)/len(ds) for _ in range(10000))
    return dict(n=len(ds),wins=wins,losses=losses,net=sum(ds),difference=sum(ds)/len(ds),ci=[bs[249],bs[9749]],sign_p=min(1.,2*sum(math.comb(n,k) for k in range(min(wins,losses)+1))/2**n) if n else 1.)


def main():
    check('policy_lock.json');check('packet_lock.json')
    rows=[]
    for i in read(D/'cohort.json')['ids']:
        d=D/'tasks'/i
        obj=json.loads(gzip.decompress((d/'packets.json.gz').read_bytes()))
        sites=gold_sites(d);sig=obj['signals']
        row=dict(id=i,paths=obj['paths'],gold=len(sites),visible=sum(p in obj['paths'] for p,n in sites),sites=sorted([p,n] for p,n in sites),signals=dict(addresses=sig['addresses'],pairs=sig['pairs']),arms={})
        for arm in ARMS:
            kept={(p,n) for p,lo,hi in obj['kept'][arm] for n in range(lo,hi+1)}
            row['arms'][arm]=dict(hit=int(bool(kept&sites)),cover=len(kept&sites),tokens=obj['tokens'][arm],changed=obj['packets'][arm]!=obj['packets']['flat'])
        rows.append(row)
    totals={}
    for arm in ARMS:
        totals[arm]={k:sum(r['arms'][arm][k] for r in rows) for k in ('hit','cover','tokens','changed')}
    by={}
    for name,rs in [('path_in_issue',[r for r in rows if r['signals']['addresses']]),('bound_pair_in_issue',[r for r in rows if r['signals']['pairs']]),('packet_changed',[r for r in rows if r['arms']['evidence']['changed']])]:
        by[name]=dict(n=len(rs),flat=sum(r['arms']['flat']['hit'] for r in rs),evidence=sum(r['arms']['evidence']['hit'] for r in rs))
    data=dict(n=len(rows),total_gold=sum(r['gold'] for r in rows),visible_lines=sum(r['visible'] for r in rows),visible_tasks=sum(bool(r['visible']) for r in rows),totals=totals,groups=by,pairs={a:pair(rows,a,'flat','hit') for a in ARMS[1:]})
    (D/'cpu_rows.json').write_text(json.dumps(rows,indent=1));(D/'cpu_results.json').write_text(json.dumps(data,indent=1))
    print(json.dumps(data))


if __name__=='__main__':main()
