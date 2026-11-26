"""Export the same rows as an optional offline standalone HTML."""
from serve import ROOT,connect,cases,detail
from contextlib import closing
import base64,json,gzip
def main():
    with closing(connect()) as db:
        listed=cases(db);details={r["g"]:detail(db,r["g"]) for r in listed}
        lines={}
        for r in db.execute("select cp,idx,line_no,fp,wp from lines order by cp,idx,ord"):
            cp,idx,ln,fp,wp=r;lines.setdefault(cp+"/"+str(idx),[]).append([ln,fp,wp])
    presets=json.loads((ROOT/"verified.json").read_bytes())["presets"]
    data=dict(cases=listed,details=details,lines=lines,presets=presets)
    raw=json.dumps(data,ensure_ascii=False,separators=(",",":")).encode()
    b64=base64.b64encode(gzip.compress(raw,mtime=0)).decode()
    template=(ROOT/"index.html").read_text(encoding="utf8")
    (ROOT/"handoff.html").write_text(template.replace("/*__SNAPSHOT__*/null",json.dumps(b64)),encoding="utf8")
if __name__=="__main__":main()
