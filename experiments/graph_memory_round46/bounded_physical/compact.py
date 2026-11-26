"""Direct sensitivity: use only the 49 joint state codes without duplicating the two output bits."""
from tempfile import TemporaryDirectory
from pathlib import Path
import random,sqlite3
from time import perf_counter_ns as wall
from operators import Reader,make,net_changes,digit,signed,code,ORI,PACK_WRITE
from run import D,BASE,read,save,sha,storage
ARMS=('deferred','dense_sql','dense_lut','scan','exact')
LUT=[int(x//7!=0)+2*int(x%7!=0) for x in range(49)]
class Dense(Reader):
    def packed_update(self,t,batch):
        rows=[];drops=[]
        for v,(dx,dy) in net_changes(batch).items():
            if dx==0 and dy==0:continue
            fetched=self.db.execute('SELECT s FROM aux WHERE t=? AND v=?',(t,v)).fetchone()
            old=fetched[0] if fetched else 0;qq=[signed(x) for x in divmod(old,7)]
            for slot,d in enumerate((dx,dy)):
                if not d:continue
                if qq[slot]>=0:qq[slot]=code(qq[slot]+d)
                elif -qq[slot]+d>0:qq[slot]=-min(3,-qq[slot]+d)
                else:
                    self.n_queries+=1
                    qq[slot]=code(self.db.execute(ORI[slot],(t,v)).fetchone()[0])
            new=7*digit(qq[0])+digit(qq[1]);assert 0<=new<=48
            if new==old:continue
            if new:rows.append((t,v,new))
            else:drops.append((t,v))
        if rows:self.db.executemany(PACK_WRITE,rows)
        if drops:self.db.executemany('DELETE FROM aux WHERE t=? AND v=?',drops)
    def read(self,t):
        if self.name=='dense_sql':return dict(self.db.execute('SELECT v,((s/7)>0) | (((s%7)>0)<<1) FROM aux WHERE t=?',(t,)))
        return {v:LUT[c] for v,c in self.db.execute('SELECT v,s FROM aux WHERE t=?',(t,))}
def execute(fixture,rep):
    rng=random.Random(46725+rep);obs={k:[] for k in ARMS};storage_rows={}
    with TemporaryDirectory(dir=D) as tmp:
        dbs={}
        for arm in ARMS:
            path=Path(tmp)/(arm+'.sqlite')
            obj=make(path,arm)
            if arm.startswith('dense'):obj=Dense(obj.db,arm)
            dbs[arm]=obj
        try:
            for t,frames in enumerate(fixture):
                gathered=[(changes,dict(want)) for changes,want in frames];order=list(ARMS);rng.shuffle(order)
                for a in order:
                    reader=dbs[a];start=wall();prev=reader.n_queries
                    for changes,want in gathered:
                        reader.apply(t,changes);assert reader.read(t)==want
                    obs[a].append([wall()-start,reader.n_queries-prev])
            for a,x in dbs.items():
                path=Path(tmp)/(a+'.sqlite');storage_rows[a]=storage(x,path)
        finally:
            for x in dbs.values():x.db.close()
    return {'traces':obs,'physical':storage_rows}
def main():
    pr=D/'COMPACT_PROTOCOL_RU.md';save(D/'compact-registration.json',{'protocol':sha(pr),'code':sha(Path(__file__)),'previous':sha(D/'results.json'),'arms':list(ARMS)})
    f=read(BASE/'normalized.json.gz')
    for rep in range(3):
        dest=D/f'dense-{rep}.json.gz';assert not dest.exists();save(dest,execute(f,rep))
if __name__=='__main__':main()

