"""Local single-session demonstration. Python standard library only."""
from argparse import ArgumentParser
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from urllib.parse import parse_qs, urlsplit
from reader import D, Reader, Grader


class Session:
    def __init__(self):
        self.reader = Reader()
        self.grader = Grader()
        self.states = self.reader.states()

    def snapshot(self, state):
        if state not in self.states:
            raise ValueError("Неизвестное состояние")
        rows = self.reader.units(state)
        top, bge = self.reader.top(state), self.reader.top(state,mode="bge")
        base = [r["unit"] for r in sorted(rows,key=lambda r:(-r["base_score"],r["unit"]))[:8]]
        # Both rankers have finished before the evaluator receives their lists.
        grades = {name:{k:self.grader.evaluate(state,seq,k) for k in (5,8)}
                  for name, seq in (("reader",top),("bge",bge),("original",base))}
        return dict(state=state,rows=rows,top=top,bge=bge,original=base,grades=grades)

    def change(self, state, op, unit=None):
        if state not in self.states or op not in ("add","remove","reset"):
            raise ValueError("Некорректное изменение")
        if op == "reset":
            self.reader.reset(state)
        else:
            if type(unit) != int:
                raise ValueError("Нужен номер фрагмента")
            self.reader.set_seen(state,unit,int(op=="add"))
        return self.snapshot(state)


def server(port, host="127.0.0.1"):
    session = Session()
    class Handler(BaseHTTPRequestHandler):
        def respond(self, data, kind="application/json; charset=utf-8", status=200):
            data = data if isinstance(data,bytes) else json.dumps(data,ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type",kind)
            self.send_header("Content-Length",str(len(data)))
            self.send_header("Cache-Control","no-store")
            self.send_header("X-Content-Type-Options","nosniff")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            route = urlsplit(self.path)
            if route.path == "/":
                return self.respond((D/"screen.html").read_bytes(),"text/html; charset=utf-8")
            if route.path == "/api/states":
                return self.respond(session.states)
            if route.path == "/api/state":
                try:
                    return self.respond(session.snapshot(parse_qs(route.query).get("id",[""])[0]))
                except ValueError as exc:
                    return self.respond({"error":str(exc)},status=400)
            self.respond({"error":"Неизвестный маршрут"},status=404)

        def do_POST(self):
            if self.path != "/api/change":
                return self.respond({"error":"Неизвестный маршрут"},status=404)
            origin = self.headers.get("Origin")
            if origin and urlsplit(origin).netloc != self.headers.get("Host"):
                return self.respond({"error":"Запрос из другого приложения"},status=403)
            try:
                n = int(self.headers.get("Content-Length",0))
                if not 0 < n < 2048 or self.headers.get_content_type() != "application/json":
                    raise ValueError("Требуется JSON")
                d = json.loads(self.rfile.read(n))
                if not isinstance(d,dict):
                    raise ValueError("Ожидается объект")
                self.respond(session.change(d.get("state"),d.get("op"),d.get("unit")))
            except (ValueError, TypeError) as exc:
                self.respond({"error":str(exc)},status=400)

    return HTTPServer((host,port),Handler)


def main():
    args = ArgumentParser(description="Локальная демоверсия читателя SERBench")
    args.add_argument("--port",type=int,default=8765)
    args.add_argument("--example",action="store_true")
    opts = args.parse_args()
    if opts.example:
        s = Session()
        for title,d in (("base",s.snapshot("s075")),("remove 19",s.change("s075","remove",19)),("restore",s.change("s075","add",19))):
            print(title,d["top"],"MSS@5/@8",[d["grades"]["reader"][k]["complete"] for k in (5,8)])
        return
    web = server(opts.port)
    print(f"http://127.0.0.1:{web.server_port}/",flush=True)
    try:
        web.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        web.server_close()


if __name__ == "__main__":
    main()
