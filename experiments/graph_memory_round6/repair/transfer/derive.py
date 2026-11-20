"""Generate transfer copies from fixed parent drivers, validating each substitution once."""
from pathlib import Path
HERE=Path(__file__).resolve().parent


def derive(name,mods):
    data=(HERE.parent/name).read_text(encoding='utf8')
    for old,new in mods:
        assert data.count(old)==1,(name,old)
        data=data.replace(old,new)
    (HERE/name).write_text(data,encoding='utf8')


if __name__=='__main__':
    derive('collect_tasks.py',[('))[:16]', '))[16:]\n    assert len(selected)==30 and len(valid)==46\n    assert set(q["instance_id"] for q in selected).isdisjoint(json.loads((D.parent/"cohort.json").read_bytes())["ids"])')])
    derive('build_memory.py',[
        ('W=D.parent.parent','W=D.parents[2]\nfrom issue_signals import parse_issue, bonus'),
        ('packets={};kept={}','signals=parse_issue(issue)\n    packets={};kept={}'),
        ('[("flat",[0.]*n),("graph",graph),("shuffled",shuf)]','[(m,[0.]*n) for m in ("flat","address","symbol","evidence")]'),
        ('c["sc"]+.85*extra[c["j"]]','c["sc"]+bonus(signals,nodes[c["j"]],c,arm)'),
        ('{"issue":issue,"packets":packets','{"issue":issue,"signals":signals,"packets":packets')])
    derive('infer.py',[('["ids"];jobs','["ids"][:12];jobs'),('for arm,packet in d["packets"].items():','for arm in ("flat","evidence"):\n            packet=d["packets"][arm]'),('127.0.0.1:18906','127.0.0.1:18907')])
    derive('grade.py',[('methods=["flat","graph","shuffled"]','methods=["flat","evidence"]'),('ids=read(D/"cohort.json")["ids"]','ids=read(D/"cohort.json")["ids"][:12]')])
    derive('start_server.ps1',[('LocalPort 18906','LocalPort 18907'),("'18906'","'18907'")])
