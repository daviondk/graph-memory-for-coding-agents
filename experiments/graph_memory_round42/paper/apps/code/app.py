"""Read-only edit replay. Snapshot witnesses are opened only by an explicit audit."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
from urllib.parse import parse_qs, urlsplit

D=Path(__file__).resolve().parent
CASES=('relocated','changed','stale')
BUDGET=2048
THRESHOLD=1024

def db(name):
    conn=sqlite3.connect((D/name).as_uri()+'?mode=ro&immutable=1',uri=True)
    conn.row_factory=sqlite3.Row
    return conn

def optimize(blocks):
    used=0;head=[]
    for x in blocks:
        if used+x['cost']>THRESHOLD:break
        head.append(x['unit']);used+=x['cost']
    states={0:(0,0)}
    for x in blocks[len(head):]:
        bit=1<<x['unit']
        for weight,(score,mask) in tuple(states.items()):
            cost=weight+x['cost'];gain=score+x['gain'];newmask=mask|bit
            if used+cost>BUDGET:continue
            old=states.get(cost)
            if old is None or (gain,-newmask)>(old[0],-old[1]):states[cost]=(gain,newmask)
    _,mask=max(states.values(),key=lambda v:(v[0],-v[1]))
    chosen=head+[x['unit'] for x in blocks[len(head):] if mask&(1<<x['unit'])]
    return {'ids':chosen,'head':head,'bytes':sum(x['cost'] for x in blocks if x['unit'] in chosen)}

def packet(case):
    conn=db('reader.sqlite')
    try:
        ev=conn.execute('SELECT low,high,line_delta,event,ack FROM receipt WHERE scenario=?',(case,)).fetchone()
        if not ev:raise ValueError('Unknown scenario')
        rows=[dict(r) for r in conn.execute('SELECT unit,low,high,cost,gain FROM block WHERE scenario=? ORDER BY unit',(case,))]
        eligible=list(conn.execute('SELECT unit FROM block WHERE scenario=? AND (high<? OR low>?) ORDER BY unit',(case,ev['low'],ev['high'])))
    finally:conn.close()
    kept={r[0] for r in eligible}
    old=optimize(rows);file_packet=optimize([]);span_packet=optimize([b for b in rows if b['unit'] in kept])
    exact=set(old['ids'])<=kept and set(span_packet['head'])<=set(old['ids'])
    assert exact==(old['ids']==span_packet['ids'])
    for b in rows:
        b['kept']=b['unit'] in kept
        shift=ev['line_delta'] if b['low']>ev['high'] else 0
        b['new_low']=b['low']+shift if b['kept'] else None;b['new_high']=b['high']+shift if b['kept'] else None
    return dict(case=case,receipt=dict(ev),blocks=rows,baseline=old,file=file_packet,span=span_packet,range_reuse=exact,file_reuse=old['ids']==file_packet['ids'])

def audit(case):
    state=packet(case);chosen=set(state['baseline']['ids']);conn=db('witness.sqlite')
    try:
        snapshot=dict(conn.execute('SELECT old_sha,new_sha,old_size,new_size,change_begin,change_end FROM snapshot WHERE scenario=?',(case,)).fetchone())
        coords={r['unit']:dict(r) for r in conn.execute('SELECT unit,old_start,old_end,new_start,new_end FROM address WHERE scenario=? ORDER BY unit',(case,))}
        lines=conn.execute('SELECT unit,n,new_n,seen,before_sha,after_sha FROM witness WHERE scenario=? ORDER BY unit,n',(case,)).fetchall()
    finally:conn.close()
    stale=[];selected_prior=[];changed_by_edit=[];invalid_before=0;invalid_after=0;chosen_lines=0
    for row in lines:
        row=dict(row);prior=row['seen']==row['before_sha'];post=row['seen']==row['after_sha']
        coord=coords[row['unit']];coord.setdefault('lines',[]).append(row)
        invalid_before+=not prior;invalid_after+=not post
        if prior and not post:changed_by_edit.append([row['unit'],row['n']])
        if row['unit'] in chosen:
            chosen_lines+=1
            if not prior:selected_prior.append([row['unit'],row['n']])
            if not post:stale.append([row['unit'],row['n']])
    assert len([b for b in state['blocks'] if b['kept']])==sum('lines' in r for r in coords.values())
    return dict(snapshot=snapshot,blocks=coords,checked=len(lines),selected_lines=chosen_lines,selected_mismatch=stale,selected_prior_mismatch=selected_prior,new_mismatch=changed_by_edit,
                prior_mismatch=invalid_before,post_mismatch=invalid_after,verified_reuse=state['range_reuse'] and not(stale or selected_prior))

class Serve(BaseHTTPRequestHandler):
    def do_GET(self):
        req=urlsplit(self.path)
        if req.path=='/':
            self.reply(200,'text/html; charset=utf-8',(D/'index.html').read_bytes());return
        endpoints={'/api/packet':packet,'/api/audit':audit}
        if req.path not in endpoints:self.reply(404,'text/plain',b'Not found');return
        case=parse_qs(req.query).get('case',[''])[0]
        if case not in CASES:self.reply(400,'text/plain',b'Unknown scenario');return
        result=endpoints[req.path](case)
        self.reply(200,'application/json; charset=utf-8',json.dumps(result,separators=(',',':')).encode())

    def reply(self,status,mime,body):
        self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
    def log_message(self,*args):pass

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8774);args=p.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Serve);print(f'http://127.0.0.1:{server.server_port}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
