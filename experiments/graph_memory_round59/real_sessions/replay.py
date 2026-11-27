"""Cost replay for passing address-equality metadata through one process restart."""
import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[1] / "graph_memory_round57" / "agent_trace" / "prefixes.json.gz"
ARMS = ("cold", "selective", "eager", "recent", "full", "unfiltered")
HORIZONS = ("1", "4", "all")
CAP = 1024


def vl(n):
    assert n >= 0
    return max(1, (n.bit_length() + 6) // 7)


def var(n):
    b = bytearray()
    while n >= 128:
        b.append(128 | (n & 127))
        n >>= 7
    b.append(n)
    return b


def getvar(b, i):
    n = 0
    shift = 0
    while True:
        value = b[i]
        i += 1
        n |= (value & 127) << shift
        if value < 128:
            return n, i
        shift += 7


@dataclass
class Image:
    size: int
    # address -> local class index and resident class -> exact text identity.
    labels: dict
    resident: dict


def empty():
    return Image(0, {}, {})


def candidates(state):
    by_text = defaultdict(list)
    for address, (uid, size, tick) in state.items():
        by_text[uid].append(address)
    found = []
    for uid, addresses in by_text.items():
        if len(addresses) < 2:
            continue
        addresses.sort()
        length = state[addresses[0]][1]
        assert all(state[a][1] == length for a in addresses)
        recency = max(state[a][2] for a in addresses)
        found.append(((len(addresses)-1)*length, recency, addresses, uid, length))
    found.sort(key=lambda item:(-item[0], -item[1], item[2]))
    return found


def encode(groups):
    """Only addresses and grouping cross the restart. No text IDs in the frame."""
    if not groups:
        return b""
    paths = sorted({path for addresses in groups for path, _ in addresses})
    ordering = {p:i for i,p in enumerate(paths)}
    frame = bytearray(b"EQ01") + var(len(paths))
    for path in paths:
        raw = path.encode()
        frame += var(len(raw)) + raw
    frame += var(len(groups))
    for addresses in groups:
        per_path = defaultdict(list)
        for path, line in addresses:
            per_path[path].append(line)
        frame += var(len(per_path))
        for path, lines in sorted(per_path.items()):
            frame += var(ordering[path]) + var(len(lines))
            prev = 0
            for line in sorted(lines):
                frame += var(line-prev)
                prev = line
    return bytes(frame)


def decode(frame):
    if not frame:
        return {}
    assert frame[:4] == b"EQ01"
    count, i = getvar(frame,4)
    paths = []
    for _ in range(count):
        size,i = getvar(frame,i)
        paths.append(frame[i:i+size].decode())
        i += size
    groups,i = getvar(frame,i)
    labels = {}
    for label in range(groups):
        nfiles,i = getvar(frame,i)
        for _ in range(nfiles):
            fid,i = getvar(frame,i)
            nrows,i = getvar(frame,i)
            number = 0
            for _ in range(nrows):
                delta,i = getvar(frame,i)
                number += delta
                key = (paths[fid],number)
                assert key not in labels
                labels[key] = label
    assert i == len(frame)
    return labels


def recipes(items, budget_test):
    frame = b""
    chosen = []
    payload = []
    for gain, _, addresses, uid, length in items:
        candidate = encode([*chosen, addresses])
        if len(candidate) > CAP or budget_test and gain <= 2*(len(candidate)-len(frame)):
            continue
        chosen.append(addresses)
        payload.append((uid,length))
        frame = candidate
    labels = decode(frame)
    assert all(labels[a] == i for i, addresses in enumerate(chosen) for a in addresses)
    lazy = Image(len(frame), labels, {})
    # Eager protocol is the same grouping followed by one length and literal per group.
    eager = Image(len(frame) + sum(vl(n)+n for _,n in payload), labels,
                  {i:uid for i,(uid,_) in enumerate(payload)})
    return lazy, eager


def latest_image(state, cap):
    """R58 compact file-grouped order and optional backward content reference."""
    if not state:
        return empty()
    latest = defaultdict(int)
    for (path,_), (_,_,seen) in state.items():
        latest[path] = max(latest[path],seen)
    paths = {}
    content_last = {}
    labels = {}
    residents = {}
    # A positional uint16 file count. Each new path pays for a uint16 row count.
    used = 2
    for (path,line), (uid,size,seen) in sorted(state.items(),
            key=lambda item:(latest[item[0][0]],item[1][2]), reverse=True):
        last_line = paths.get(path,0)
        d = line-last_line
        addr = vl(2*d if d>=0 else -2*d-1)
        literal = vl(size*2) + size
        row = len(labels)
        content_cost = literal
        if uid in content_last:
            content_cost = min(literal, vl(2*(row-content_last[uid]-1)+1))
        extra = addr + content_cost
        if path not in paths:
            path_bytes = len(path.encode())
            extra += vl(path_bytes)+path_bytes+2
        if cap is not None and used+extra > cap:
            continue
        used += extra
        labels[path,line] = row
        residents[row] = uid
        paths[path] = line
        content_last[uid] = row
    return Image(used,labels,residents) if labels else empty()


def projection(events):
    n = sum(len(e)==3 for e in events)
    midpoint = n//2
    end = 0
    if midpoint:
        seen = 0
        for i,e in enumerate(events):
            seen += len(e)==3
            if seen == midpoint:
                end = i+1
                break
    cells = {}
    tick = 0
    for event in events[:end]:
        if event[0] == "barrier":
            cells.clear()
        if len(event)==3:
            _,p,lines = event
            for ln,uid,size in lines:
                tick += 1
                cells[p,ln] = (uid,size,tick)
    return cells, events[end:], midpoint


def pack_charge(returned, dictionary, count):
    size = 0
    for uid,length in returned:
        literal = vl(2*length)+length
        tag = vl(2*(count-dictionary[uid])-1) if uid in dictionary else literal
        size += min(literal,tag)
        dictionary[uid] = count
        count += 1
    return size,count


def address_charge(path, nums):
    if not nums:
        return 0
    path_len = len(path.encode())
    size = vl(path_len)+path_len+vl(len(nums))
    prev = 0
    for n in sorted(nums):
        size += vl(n-prev)
        prev = n
    return size


class Reader:
    def __init__(self, img):
        self.labels = img.labels.copy()
        self.resident = img.resident.copy()
        self.local = {}
        self.transport = {}
        self.transmitted = 0

    def clear(self):
        self.labels.clear()
        self.resident.clear()
        self.local.clear()

    def window(self, path, lines):
        # No content ID or size is passed to the planner. Request one representative per
        # unresolved group and independently request every other unknown address.
        wanted = [n for n,_,_ in lines]
        promised = {}
        fetch = []
        for n in wanted:
            key = (path,n)
            if key in self.local:
                continue
            g = self.labels.get(key)
            if g is not None and (g in self.resident or g in promised):
                continue
            if g is not None:
                promised[g] = key
            fetch.append(n)
        source = {n:(uid,size) for n,uid,size in lines}
        assert len(source) == len(lines)
        returned = [source[n] for n in fetch]
        for n in fetch:
            uid = source[n][0]
            key = (path,n)
            self.local[key] = uid
            if key in self.labels:
                self.resident[self.labels[key]] = uid
        wrong = 0
        for n,uid,_ in lines:
            key = (path,n)
            reply = self.local[key] if key in self.local else self.resident[self.labels[key]]
            wrong += reply != uid
            self.local[key] = reply
        per_window,_ = pack_charge(returned,{},0)
        cross,self.transmitted = pack_charge(returned,self.transport,self.transmitted)
        return [len(fetch),sum(s for _,s in returned),per_window,cross,address_charge(path,fetch),wrong]


def trace_record(t):
    state, future, mid = projection(t["events"])
    items = candidates(state)
    select,eager = recipes(items,True)
    basic,_ = recipes(items,False)
    images = dict(cold=empty(),selective=select,eager=eager,recent=latest_image(state,CAP),
                  full=latest_image(state,None),unfiltered=basic)
    readers = {k:Reader(i) for k,i in images.items()}
    windows = []
    first_barrier = None
    for event in future:
        if event[0] == "barrier":
            if first_barrier is None:
                first_barrier = len(windows)
            for reader in readers.values():
                reader.clear()
        if len(event)==3:
            _,path,lines = event
            windows.append([readers[a].window(path,lines) for a in ARMS])
    return dict(repo=t["repo"],issue=t["issue"],actor=t["actor"],past_windows=mid,
                first_barrier=first_barrier,post_windows=len(windows),
                image={a:[i.size,len(i.labels),len(set(i.labels.values()))] for a,i in images.items()},
                windows=windows)


def read_json(path):
    return json.loads(gzip.decompress(path.read_bytes()) if path.suffix==".gz" else path.read_bytes())


def save(path, obj, verify):
    if verify:
        assert obj == read_json(path)
        return
    raw = (json.dumps(obj,sort_keys=True,separators=(",",":"))+"\n").encode()
    path.write_bytes(gzip.compress(raw,mtime=0) if path.suffix==".gz" else raw)


def costs(row, horizon):
    rows = row["windows"] if horizon=="all" else row["windows"][:int(horizon)]
    out = {}
    for i, arm in enumerate(ARMS):
        snap = row["image"][arm][0]
        n,raw,wire,cross,request,wrong = [sum(w[i][j] for w in rows) for j in range(6)]
        out[arm] = dict(snapshot=snap, reads=n, raw=raw, responses=wire, cross=cross,
                        requests=request, wrong=wrong, total=2*snap+wire, duplex=2*snap+wire+request,
                        cross_total=2*snap+cross, raw_total=2*snap+raw)
    return out


def uncertainty(deltas):
    arr = np.array(list(deltas.values()))
    if not len(arr):
        return {}
    rng = np.random.default_rng(59021)
    counts = rng.multinomial(len(arr),np.ones(len(arr))/len(arr),size=20000)
    means = counts @ arr / len(arr)
    return dict(issue_mean=float(np.mean(arr)),ci95_mean=np.quantile(means,[.025,.975]).tolist(),
                win=int((arr<0).sum()),tie=int((arr==0).sum()),loss=int((arr>0).sum()))


def summary(rows,horizon):
    totals = {a:Counter() for a in ARMS}
    issues = Counter()
    deltas = []
    for r in rows:
        values = costs(r,horizon)
        d = values["selective"]["total"]-values["cold"]["total"]
        issues[r["issue"]] += d
        deltas.append(d)
        for a,v in values.items():
            totals[a].update(v)
    return dict(sessions=len(rows),issues=len(issues),metrics={k:dict(v) for k,v in totals.items()},
                win=sum(d<0 for d in deltas),tie=deltas.count(0),loss=sum(d>0 for d in deltas),
                primary_minus_cold_issue=uncertainty(issues))


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--verify",action="store_true")
    args=p.parse_args()
    records = [trace_record(t) for t in read_json(SOURCE)]
    assert len(records)==108
    assert all(len(r["windows"])==r["post_windows"] for r in records)
    assert all(r["image"][a][0] <= CAP for r in records for a in ("recent","selective","unfiltered"))
    assert all(all(v[-1]==0 for v in window) for r in records for window in r["windows"]), "stale response"
    relevant = [r for r in records if r["image"]["selective"][0]]
    results = dict(all={h:summary(records,h) for h in HORIZONS},
                   nonempty={h:summary(relevant,h) for h in HORIZONS},
                   repos={repo:summary([r for r in records if r["repo"]==repo],"all") for repo in sorted({r["repo"] for r in records})},
                   peak={a:max(r["image"][a][0] for r in records) for a in ARMS},
                   source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                   protocol_sha256_lf=hashlib.sha256((HERE/"PROTOCOL_RU.md").read_text(encoding="utf8").encode()).hexdigest())
    raw = dict(arms=list(ARMS), image_fields=["bytes","addresses","classes"], window_fields=[
        "fetched_lines","raw_fresh_bytes","response_bytes","cross_window_response_bytes","request_address_bytes","mismatches"],
        traces=records)
    save(HERE/"outcomes.json.gz",raw,args.verify)
    save(HERE/"results.json",results,args.verify)
    print("sessions",len(records),"nonempty",len(relevant),"post",sum(r["post_windows"] for r in records))
    for a,v in results["all"]["all"]["metrics"].items():
        print(a,v)
    print(results["all"]["all"]["primary_minus_cold_issue"])


if __name__=="__main__":
    main()
