"""Generate the two small, reviewable diffs against the frozen strict writer and the prior public-trajectory grader."""
from pathlib import Path
D=Path(__file__).resolve().parent
S=D.parent/"serialized_writer"; O=D.parent/"real_swe"
writer=(S/"writer.py").read_text(encoding="utf8")
assert writer.count('arm=="typed"')==2
writer=writer.replace('arm=="typed"','arm in ("typed","mixed")')
writer=writer.replace('if arm=="lru":return list(reversed(rank))','''if arm=="mixed":
        age=max(r[3] for r in rr)
        recent_bytes=sum(len((f"@@ {r[0]} {r[1]}..{r[2]} @@\\n"+r[4]+"\\n").encode("utf8")) for r in rr if r[3]==age)
        # The counter is a write-only diagnostic, reset for each shard; it is never used to decide a policy.
        selected="lru" if recent_bytes<=4096 else "typed"
        branch_log[selected]+=1
        arm=selected
    if arm=="lru":return list(reversed(rank))''')
writer=writer.replace('def h(x):','branch_log=Counter()\ndef h(x):')
writer=writer.replace('wm=read(R2/', 'branch_log.clear()\n    wm=read(R2/')
writer=writer.replace('transition_ns=dict(times))','transition_ns=dict(times),gate_calls=dict(branch_log))')
(D/"writer_followup.py").write_text(writer,encoding="utf8")
s=(O/"transfer.py").read_text(encoding="utf8").replace('import writer as w','import writer_followup as w')
s=s.replace('w.ARMS=("lru","point","typed")','w.ARMS=("lru","point","typed","mixed")')
s=s.replace('("point","lru")','("point","lru"),("mixed","lru"),("mixed","typed"),("mixed","point")')
s=s.replace('D/"choose_issues.py",D/"acquire.py",D/"transfer.py",','D/"select_followup.py",D/"acquire_followup.py",D.parent/"real_swe"/"acquire.py",D/"writer_followup.py",D/"transfer_followup.py",')
s=s.replace('assert all(h((D/n).read_bytes())==s for n,s in read(D/"checkpoint_lock.json").items())','assert all(h((D/n).read_bytes())==s for n,s in read(D/"checkpoint_lock.json").items())\n        w.ARMS=("lru","point","typed","mixed")')
(D/"transfer_followup.py").write_text(s,encoding="utf8")

