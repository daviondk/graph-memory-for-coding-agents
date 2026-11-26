"""Serve the local ISETrace demo; selection and grading have separate endpoints."""
import argparse
from http.server import BaseHTTPRequestHandler,HTTPServer
import json
from time import perf_counter_ns
from urllib.parse import parse_qs,urlsplit
from reader import D,Reader,Evaluator,BUDGETS

class Demo(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            u=urlsplit(self.path);args=parse_qs(u.query,strict_parsing=True)
            if u.path=='/' and not args:
                return self.send(200,(D/'index.html').read_bytes(),'text/html; charset=utf-8')
            if u.path=='/api/queries' and not args:return self.data({'queries':self.server.reader.queries()})
            if u.path not in {'/api/packet','/api/evaluate'}:return self.data({'error':'unknown resource'},404)
            if set(args)-{'q','budget','exclude'} or any(len(v)!=1 for v in args.values()):raise ValueError('unexpected parameter')
            q=args['q'][0];budget=int(args['budget'][0]);exclude=args.get('exclude',[None])[0];r=self.server.reader
            started=perf_counter_ns();packet=r.choose(q,budget,exclude);micros=(perf_counter_ns()-started)/1000
            if u.path=='/api/evaluate':
                evaluator=Evaluator()
                try:return self.data(evaluator.evaluate(r,packet))
                finally:evaluator.db.close()
            baseline=r.choose(q,2048);state=set(packet['ids']);original=set(baseline['ids'])
            return self.data(dict(packet=packet,items=r.explain(packet),sources=r.sources(q),added=sorted(state-original),removed=sorted(original-state),latency_us=micros))
        except (KeyError,TypeError,ValueError) as exc:return self.data({'error':str(exc)},400)
    def data(self,value,status=200):return self.send(status,json.dumps(value,ensure_ascii=False,allow_nan=False).encode(),'application/json; charset=utf-8')
    def send(self,status,body,content):
        self.send_response(status);self.send_header('Content-Type',content);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(body)
    def log_message(self,*args):pass

def server(port):
    http=HTTPServer(('127.0.0.1',port),Demo);http.reader=Reader();return http
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8769);args=p.parse_args();http=server(args.port)
    print(f'http://127.0.0.1:{http.server_port}',flush=True)
    try:http.serve_forever()
    except KeyboardInterrupt:pass
    finally:http.reader.db.close();http.server_close()
