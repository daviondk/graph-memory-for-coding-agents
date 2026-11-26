"""Source-weight interval lookups and a separate, integer-only packet oracle."""
import argparse
from bisect import bisect_right
from contextlib import closing
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import sqlite3
import struct
from time import perf_counter_ns
from urllib.parse import parse_qs, urlsplit

BASE = Path(__file__).resolve().parent
LOW, HIGH = -(1 << 30), 1 << 30
SCALE, BUDGET, PREFIX = 1 << 32, 2048, 1024

def connect(path):
    return sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro&immutable=1', uri=True)

def unpack(blob):
    return [i for i, in struct.iter_unpack('<H', blob)]

def full_optimum(reader, query, source, delta):
    """Only node and span records are used. An ID gains delta once per source."""
    rows = reader.execute('SELECT id,tokens,utility FROM node WHERE q=? ORDER BY rank', (query,)).fetchall()
    touched = {i for i, in reader.execute('SELECT DISTINCT id FROM span WHERE q=? AND source=?', (query, source))}
    head = []
    spent = 0
    for ident, price, _ in rows:
        if spent + price > PREFIX:
            break
        spent += price
        head.append(ident)
    tail = rows[len(head):]
    capacity = BUDGET - spent
    best = [0] * (capacity + 1)
    history = []
    for ident, price, utility in tail:
        value = round(utility * SCALE) + (delta if ident in touched else 0)
        decisions = bytearray(capacity + 1)
        for w in range(capacity, price - 1, -1):
            alternative = best[w-price] + value
            if alternative > best[w]:
                best[w] = alternative
                decisions[w] = 1
        history.append(decisions)
    chosen = []
    for (ident, price, _), decisions in zip(reversed(tail), reversed(history)):
        if decisions[capacity]:
            chosen.append(ident)
            capacity -= price
    return head + chosen[::-1]

def source_choices(index, reader, query):
    options = index.execute('SELECT source,count(*) AS n FROM edge WHERE q=? GROUP BY source ORDER BY n DESC,source',
                            (query,)).fetchall()
    if not options:
        raise ValueError('Unknown projection')
    origin = {s:(role,pos) for s,role,pos in reader.execute('SELECT source,role,position FROM origin WHERE q=?', (query,))}
    return [dict(id=s, intervals=n, role=origin[s][0], position=origin[s][1]) for s,n in options]

def lookup(index, reader, query, source, delta, verify=False):
    if not LOW <= delta <= HIGH:
        raise ValueError('Weight is outside the Q32 domain')
    rows = index.execute('SELECT start,packet_id FROM edge WHERE q=? AND source=? ORDER BY start',
                         (query,source)).fetchall()
    if not rows:
        raise ValueError('Unknown projection or source')
    starts = [start for start,_ in rows]
    i = bisect_right(starts,delta)-1
    baseline = bisect_right(starts,0)-1
    tokens = dict(reader.execute('SELECT id,tokens FROM node WHERE q=?', (query,)))
    def describe(weight):
        packet,blob = index.execute(
            'SELECT p.id,p.members FROM edge e JOIN packet p ON p.id=e.packet_id '
            'WHERE e.q=? AND e.source=? AND e.start<=? ORDER BY e.start DESC LIMIT 1',
            (query,source,weight)).fetchone()
        members = unpack(blob)
        return dict(id=packet, members=members, tokens=sum(tokens[n] for n in members))
    after = describe(delta)
    before = after if i==baseline else describe(0)
    lo = starts[i]
    hi = starts[i+1]-1 if i+1 < len(rows) else HIGH
    states = [dict(lo=s, hi=starts[j+1]-1 if j+1<len(starts) else HIGH, id=packet)
              for j,(s,packet) in enumerate(rows)]
    response = dict(query=query, source=source, delta=delta, low=LOW, high=HIGH, budget=BUDGET, threshold=PREFIX,
                    current=i, baseline_interval=baseline, intervals=states, lo=lo, hi=hi,
                    previous=lo-1 if i else None, next=hi+1 if i+1 < len(rows) else None,
                    before=before, after=after, unchanged=before['members']==after['members'],
                    removed=[n for n in before['members'] if n not in after['members']],
                    added=[n for n in after['members'] if n not in before['members']])
    if verify:
        start = perf_counter_ns()
        direct = full_optimum(reader, query, source, delta)
        response['verification'] = dict(equal=after['members']==direct, members=direct,
                                        tokens=sum(tokens[n] for n in direct), microseconds=(perf_counter_ns()-start)//1000)
    return response

def handle_weights(handler, *, index_path=None, reader_path=None):
    """Return False for unrelated routes. Uses only the BaseHTTPRequestHandler interface."""
    url = urlsplit(handler.path)
    if url.path != '/weights' and not url.path.startswith('/api/weights/'):
        return False
    def send(code, content, mime='application/json; charset=utf-8'):
        body = content if isinstance(content,bytes) else json.dumps(content, ensure_ascii=False).encode()
        handler.send_response(code)
        handler.send_header('Content-Type',mime)
        handler.send_header('Cache-Control','no-store')
        handler.send_header('Content-Length',str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)
    if url.path == '/weights':
        send(200,(BASE/'weights.html').read_bytes(),'text/html; charset=utf-8')
        return True
    options = parse_qs(url.query)
    try:
        with closing(connect(index_path or BASE/'runtime/view.sqlite')) as index, closing(connect(reader_path or BASE/'runtime/reader.sqlite')) as reader:
            if url.path == '/api/weights/catalog':
                queries = [q for q, in index.execute('SELECT DISTINCT q FROM edge ORDER BY q')]
                send(200,dict(queries=queries, low=LOW, high=HIGH))
            elif url.path == '/api/weights/sources':
                q = options['q'][0]
                send(200,dict(query=q,sources=source_choices(index,reader,q)))
            elif url.path in ('/api/weights/packet','/api/weights/verify'):
                send(200,lookup(index,reader,options['q'][0],options['s'][0],int(options['delta'][0]),
                                verify=url.path.endswith('/verify')))
            else:
                send(404,dict(error='Unknown resource'))
    except (KeyError,ValueError) as exc:
        send(400,dict(error=str(exc)))
    except sqlite3.OperationalError:
        send(503,dict(error='The interval index or reader database is unavailable'))
    return True

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8784)
    parser.add_argument('--index',type=Path,default=BASE/'runtime/view.sqlite')
    parser.add_argument('--reader',type=Path,default=BASE/'runtime/reader.sqlite')
    args = parser.parse_args()
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if not handle_weights(self,index_path=args.index,reader_path=args.reader):
                self.send_error(404)
        def log_message(self,*args):
            pass
    with HTTPServer(('127.0.0.1',args.port),Handler) as server:
        server.serve_forever()
