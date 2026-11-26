"""English demo of a protected-prefix materialized view, served only on localhost."""
import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path
from urllib.parse import parse_qs,urlsplit

D=Path(__file__).resolve().parent
runtime=D/'runtime' if (D/'runtime'/'reader.sqlite').is_file() else D.parent/'provenance_packet_demo'
sys.path.insert(0,str(runtime))
from reader import Reader,Evaluator,BUDGETS
from weights import handle_weights
from joint import handle_joint
from observed import handle_observed

class View:
    def __init__(self):self.r=Reader();self.cache={}
    def prepare(self,q,b):
        if (q,b) not in self.cache:
            packet=self.r.choose(q,b);base=set(packet['ids']);rows=self.r.db.execute('SELECT id,tokens FROM node WHERE q=? ORDER BY rank',(q,)).fetchall();n=len(packet['head']);barrier=rows[n][0] if n<len(rows) else None
            dependencies={s['id']:[False,False] for s in self.r.sources(q)}
            for i,s in self.r.db.execute('SELECT id,source FROM span WHERE q=?',(q,)):
                dependencies[s][0]|=i in base;dependencies[s][1]|=i==barrier
            self.cache[q,b]=packet,barrier,dependencies
        return self.cache[q,b]
    def state(self,q,b,source,mode,grade):
        if q not in self.r.queries() or b not in BUDGETS or mode not in ('certificate','full'):raise ValueError('unknown selection')
        base,barrier,flags=self.prepare(q,b)
        if source and source not in flags:raise ValueError('unknown source')
        sel,bound=flags[source] if source else (False,False);reuse=bool(source and mode=='certificate' and not (sel or bound));packet=base if reuse or not source else self.r.choose(q,b,source)
        answer=dict(q=q,budget=b,mode=mode,source=source,barrier=barrier,dep_selected=sel,dep_barrier=bound,action='Original packet' if not source else 'Reuse cached packet' if reuse else 'Recompute packet',tokens=packet['tokens'],total=len(packet['ids']),added=sorted(set(packet['ids'])-set(base['ids'])),removed=sorted(set(base['ids'])-set(packet['ids'])),items=self.r.explain(packet),sources=[dict(s,selected=flags[s['id']][0],barrier=flags[s['id']][1]) for s in self.r.sources(q)])
        if grade:
            exact=self.r.choose(q,b,source or None);ev=Evaluator()
            try:answer['audit']=dict(full_matches=exact['ids']==packet['ids'],**ev.evaluate(self.r,packet))
            finally:ev.db.close()
        return answer

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if handle_observed(self) or handle_joint(self) or handle_weights(self):return
        try:
            path=urlsplit(self.path);a=parse_qs(path.query);view=self.server.view
            if path.path=='/':return self.send(200,'text/html; charset=utf-8',(D/'console.html').read_bytes())
            if path.path=='/api/queries':return self.data(dict(queries=view.r.queries()))
            if path.path not in ('/api/packet','/api/audit'):return self.data({'error':'unknown resource'},404)
            return self.data(view.state(a['q'][0],int(a['b'][0]),a.get('s',[''])[0],a.get('mode',['certificate'])[0],path.path=='/api/audit'))
        except (ValueError,KeyError) as exc:return self.data({'error':str(exc)},400)
    def send(self,code,mime,body):
        self.send_response(code);self.send_header('Content-Type',mime);self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def data(self,v,code=200):return self.send(code,'application/json; charset=utf-8',json.dumps(v).encode())
    def log_message(self,*args):pass

if __name__=='__main__':
    cli=argparse.ArgumentParser();cli.add_argument('--port',type=int,default=8770);args=cli.parse_args();s=HTTPServer(('127.0.0.1',args.port),Handler);s.view=View();print(f'http://127.0.0.1:{s.server_port}',flush=True)
    try:s.serve_forever()
    except KeyboardInterrupt:pass
    finally:s.view.r.db.close();s.server_close()
