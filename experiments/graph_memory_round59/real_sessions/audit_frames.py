"""Independently build literal/reference frames using synthetic equality-preserving bytes."""
from collections import Counter
from replay import CAP, SOURCE, getvar, latest_image, projection, read_json, var


def check(state, cap):
    img = latest_image(state,cap)
    if img.size == 0:
        assert not img.labels
        return
    by_length = Counter()
    symbols = {}
    for uid,size,_ in state.values():
        if uid not in symbols:
            # Real bytes are absent; the sole property used by this format is equality.
            symbols[uid] = by_length[size].to_bytes(size,"little")
            by_length[size] += 1
    recency = {}
    for (path,_),(_,_,tick) in state.items():
        recency[path] = max(recency.get(path,0),tick)
    files = sorted({p for p,_ in img.labels},key=recency.get,reverse=True)
    frame = bytearray(len(files).to_bytes(2,"little"))
    seen = {}
    count = 0
    for path in files:
        name = path.encode()
        keys = sorted((k for k in img.labels if k[0]==path),
                      key=lambda k:state[k][2], reverse=True)
        frame += var(len(name))+name+len(keys).to_bytes(2,"little")
        previous = 0
        for address in keys:
            number = address[1]
            uid = state[address][0]
            delta = number-previous
            frame += var(2*delta if delta>=0 else -2*delta-1)
            previous = number
            literal = var(2*len(symbols[uid]))+symbols[uid]
            pointer = var(2*(count-seen[uid])-1) if uid in seen else literal
            frame += pointer if len(pointer)<len(literal) else literal
            count += 1
            seen[uid] = count-1
    assert len(frame) == img.size
    i = 2
    decoded = []
    for _ in range(int.from_bytes(frame[:2],"little")):
        n,i = getvar(frame,i)
        name = bytes(frame[i:i+n]).decode()
        i += n
        nrows = int.from_bytes(frame[i:i+2],"little")
        i += 2
        line = 0
        for _ in range(nrows):
            d,i = getvar(frame,i)
            line += -(d//2)-1 if d%2 else d//2
            tag,i = getvar(frame,i)
            if tag%2:
                value = decoded[-(tag//2)-1]
            else:
                value = bytes(frame[i:i+tag//2])
                i += tag//2
            assert value == symbols[state[name,line][0]]
            decoded.append(value)
    assert i == len(frame) and len(decoded) == len(img.labels)


if __name__=="__main__":
    traces = read_json(SOURCE)
    for t in traces:
        cells,_,_ = projection(t["events"])
        for cap in (CAP,None):
            check(cells,cap)
    print("Round-trip lengths and decoded equalities verified for",2*len(traces),"literal/reference images.")
