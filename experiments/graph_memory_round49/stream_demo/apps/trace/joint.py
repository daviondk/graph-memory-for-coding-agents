"""Serve materialized packet planes with a separately recomputed audit."""
from contextlib import closing
from urllib.parse import parse_qs, urlsplit
from weights import BASE, LOW, HIGH, connect, unpack, full_optimum

EXAMPLE = dict(pair=95, x=1 << 28, y=1 << 28)

def packet_at(index, pair, x, y):
    row = index.execute(
        "SELECT k.id,k.members FROM plane p JOIN packet k ON p.packet=k.id "
        "WHERE p.pair_id=? ORDER BY p.v+p.a*?+p.b*? DESC,p.priority LIMIT 1",
        (pair, x, y)).fetchone()
    return {"id": row[0], "members": unpack(row[1])}

def state(index, reader, pair, x, y, audit):
    if not all(LOW <= weight <= HIGH for weight in (x, y)):
        raise ValueError("Both shifts must lie in the displayed domain")
    row = index.execute("SELECT q,s,t FROM pair WHERE id=?", (pair,)).fetchone()
    if row is None:
        raise ValueError("Unknown source pair")
    q, s, t = row
    prices = dict(reader.execute("SELECT id,tokens FROM node WHERE q=?", (q,)))
    packets = {name: packet_at(index,pair,dx,dy) for name,dx,dy in
               (("base",0,0),("first",x,0),("second",0,y),("joint",x,y))}
    for data in packets.values():
        data["tokens"] = sum(prices[item] for item in data["members"])
    result = dict(pair=pair, query=q, sources=[s,t], x=x, y=y, packets=packets)
    result["planes"] = index.execute(
        "SELECT a,b,v,packet FROM plane WHERE pair_id=? ORDER BY priority", (pair,)).fetchall()
    if audit:
        ids = full_optimum(reader,q,s,x,second_source=t,second_delta=y)
        result["audit"] = dict(equal=ids==packets["joint"]["members"], members=ids)
    return result

def handle_joint(handler):
    route = urlsplit(handler.path)
    if route.path == "/joint":
        handler.send(200,"text/html; charset=utf-8",(BASE/"joint.html").read_bytes())
        return True
    if not route.path.startswith("/api/joint/"):
        return False
    try:
        with closing(connect(BASE/"runtime/planes.sqlite")) as index:
            if route.path == "/api/joint/catalog":
                pairs = index.execute("SELECT id,q FROM pair ORDER BY id").fetchall()
                handler.data(dict(pairs=pairs, example=EXAMPLE))
            elif route.path in ("/api/joint/state","/api/joint/audit"):
                args=parse_qs(route.query)
                with closing(connect(BASE/"runtime/reader.sqlite")) as reader:
                    handler.data(state(index,reader,*(int(args[key][0]) for key in ("pair","x","y")),
                                       audit=route.path.endswith("/audit")))
            else:
                handler.data(dict(error="Unknown joint route"),404)
    except (KeyError,ValueError) as exc:
        handler.data(dict(error=str(exc)),400)
    return True
