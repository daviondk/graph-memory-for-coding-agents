"""Serialize verified source observations and an equal-byte chronological control."""
import gzip,hashlib,json
from pathlib import Path
D=Path(__file__).resolve().parent
BASE=Path("D:/CodexResearch/x20-r38-traitlets-paired")
def sha(b):return hashlib.sha256(b).hexdigest()
def write(name,data): (D/name).write_bytes((json.dumps(data,ensure_ascii=False,indent=2,sort_keys=True)+"\n").encode())
def pack():
    plan=json.loads((D/"plan.json").read_bytes())
    assert sha((D/"gateway.py").read_bytes())==plan["gateway"]
    scout=BASE/"scout"
    events=[json.loads(line) for line in (scout/"tool-log.jsonl").read_text(encoding="utf8").splitlines()]
    displayed={tuple(pair) for e in events for pair in e["displayed"]}
    selected=json.loads((D/"scout-selections.json").read_bytes())
    cards=[]
    for r in selected:
        assert r["hi"]>=r["lo"] and r["hi"]-r["lo"]<5
        assert all((r["path"],k) in displayed for k in range(r["lo"],r["hi"]+1))
        src=(scout/"repo"/r["path"]).read_text(encoding="utf8").splitlines()
        cards.append(f'{r["path"]}:{r["lo"]}-{r["hi"]} | {r["note"]}')
    # Keep each source pointer + scout observation intact. Use remaining space for complete exact source lines in order.
    body="\n".join(cards)
    excerpts=[]
    for r in selected:
        lines=(scout/"repo"/r["path"]).read_text(encoding="utf8").splitlines()
        for i in range(r["lo"],r["hi"]+1):
            line=f'{r["path"]}:{i} | {lines[i-1]}'
            if len(("\n".join([body,*excerpts,line])).encode())<=plan["evidence_cap_bytes"]:excerpts.append(line)
    packet="\n".join([body,*excerpts])
    chronological="\n".join(e["output"] for e in events).encode()
    raw=chronological[-len(packet.encode()):].decode("utf8",errors="ignore")
    arms={"empty":"","cards":packet,"recency":raw}
    records={}
    for actor,arm in plan["roles"].items():
        data=arms[arm].encode()
        (BASE/actor/"memory.txt").write_bytes(data)
        records[actor]=dict(arm=arm,size=len(data),sha256=sha(data),text=arms[arm])
    write("packets.json",records)
    log=(scout/"tool-log.jsonl").read_bytes()
    (D/"scout-log.jsonl.gz").write_bytes(gzip.compress(log,mtime=0))
    write("pack-seal.json",dict(scout_actions=len(events),scout_visible_bytes=sum(e["bytes"] for e in events),
          selected=len(selected),packets=sha((D/"packets.json").read_bytes()),script=sha(Path(__file__).read_bytes()),
          scout_log=sha(log),plan=sha((D/"plan.json").read_bytes()),selection=sha((D/"scout-selections.json").read_bytes())))
    print({k:(v["arm"],v["size"]) for k,v in records.items()})
if __name__=="__main__":
    pack()

