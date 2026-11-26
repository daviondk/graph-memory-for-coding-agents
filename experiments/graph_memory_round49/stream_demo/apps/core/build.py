"""Create a small SQLite projection from the registered seed 13 reader input."""
from pathlib import Path
import argparse,gzip,hashlib,json,sqlite3
D=Path(__file__).resolve().parent
def h(s):return hashlib.sha256(s).hexdigest()
def main():
    parser=argparse.ArgumentParser();parser.add_argument('source',type=Path);a=parser.parse_args()
    raw=a.source.read_bytes()
    assert h(raw)==json.loads((a.source.parent/'sources-13.json').read_bytes())['input']
    rows=json.loads(gzip.decompress(raw));keys=sorted(rows,key=lambda q:(len(rows[q]['cost']),q));assert len(keys)==2000
    path=D/'core.sqlite';assert not path.exists()
    con=sqlite3.connect(path)
    con.executescript('CREATE TABLE example (name TEXT PRIMARY KEY, query TEXT, trajectory TEXT, total INTEGER, costs TEXT); CREATE TABLE state (name TEXT,pct INTEGER,event INTEGER,ordered TEXT,utility TEXT,PRIMARY KEY(name,pct));')
    panel={}
    for i,name in enumerate(('short','medium','long')):
        group=keys[i*len(keys)//3:(i+1)*len(keys)//3]
        q=min(group,key=lambda q:h(('r49-core-panel-v1/'+q).encode()))
        v=rows[q];c=v['cost'];assert all(type(y)==int and y>=0 for y in c)
        con.execute('INSERT INTO example VALUES (?,?,?,?,?)',(name,q,v['t'],len(c),json.dumps(c,separators=(',',':'))))
        for pct,at,ids,u,_ in v['states']:
            assert len(ids)==len(u)==len(set(ids)) and min(u)>=0
            con.execute('INSERT INTO state VALUES (?,?,?,?,?)',(name,pct,at,json.dumps(ids,separators=(',',':')),json.dumps(u,separators=(',',':'))))
        panel[name]=dict(query=q,total=len(c),stratum=len(group),pool_range=[len(rows[group[0]]['cost']),len(rows[group[-1]]['cost'])])
    con.commit();con.execute('VACUUM');con.close()
    (D/'projection.json').write_text(json.dumps(dict(source=h(raw),sqlite=h(path.read_bytes()),panel=panel,selection=h((D/'SELECTION.md').read_bytes())),indent=2)+'\n',encoding='utf8')
if __name__=='__main__':main()
