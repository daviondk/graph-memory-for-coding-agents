"""An interactive local view of known value transfers at a selected execution step."""
import argparse,hashlib,json,sqlite3
from contextlib import closing
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs,urlsplit
D=Path(__file__).resolve().parent
def snapshot(case,step,audit):
    with closing(sqlite3.connect((D/'flow.sqlite').as_uri()+'?immutable=1&mode=ro',uri=True)) as db:
        row=db.execute('select n,focus from scenario where id=?',(case,)).fetchone()
        if not row:raise ValueError('Unknown trace')
        n,focus=row
        step=focus if step is None else step
        if not 1<=step<=n:raise ValueError('Step outside trace')
        data=db.execute('select step,src,dst,weight from delta where case_id=? and step<=? order by step,idx',(case,step)).fetchall()
        groups=[[] for _ in range(step)]
        for idx,a,b,v in data:groups[idx-1].append((a,b,v))
        balance={};history={};old={};active={}
        for changes in groups:
            old=active.copy()
            for a,b,w in changes:
                for key,slot in ((a,0),(b,1)):
                    balance.setdefault(key,[0,0])[slot]+=w
            assert all(x>=0 and y>=0 for x,y in balance.values())
            active={k:int(x>0)+2*int(y>0) for k,(x,y) in balance.items() if x or y}
            for k,v in active.items():history[k]=history.get(k,0)|v
        result=dict(step=step,total=n,focus=focus,active=active,ever=history,previous=old,changes=groups[-1])
        if audit:
            expected=db.execute('select digest from expected where case_id=? and step=?',(case,step)).fetchone()[0]
            digest=hashlib.sha256(json.dumps(sorted(active.items()),separators=(',',':')).encode()).hexdigest()
            result['audit']=dict(matches=digest==expected,nodes=len(active),digest=digest)
        return result
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        uri=urlsplit(self.path);status=200
        if uri.path=='/':data=(D/'index.html').read_bytes();mime='text/html; charset=utf-8'
        elif uri.path in ('/snapshot','/audit'):
            try:
                q=parse_qs(uri.query)
                obj=snapshot(q['case'][0],int(q['step'][0]) if 'step' in q else None,uri.path=='/audit')
            except (KeyError,ValueError,IndexError):obj={'error':'Unknown trace or step'};status=400
            data=json.dumps(obj).encode();mime='application/json'
        else:self.send_error(404);return
        self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def log_message(self,*args):pass
if __name__=='__main__':
    cli=argparse.ArgumentParser();cli.add_argument('--port',type=int,default=8780)
    with ThreadingHTTPServer(('127.0.0.1',cli.parse_args().port),Handler) as app:
        print(f'http://127.0.0.1:{app.server_port}',flush=True)
        try:app.serve_forever()
        except KeyboardInterrupt:pass
