"""Read two ZIP members by verified range; unpickle only primitive types; write Arrow for blind column projection."""
import gzip,io,json,pickle,sys,zipfile,zlib
from pathlib import Path
from run import D,R,E,load,now,save,sha
import pyarrow as pa
import pyarrow.parquet as pq
sys.path.append(str(E/'.venv/Lib/site-packages'))
from archive_probe import Remote,URL

class Restricted(pickle.Unpickler):
    def find_class(self,module,name):raise pickle.UnpicklingError('Only primitive data accepted')

def main():
    dest=D/'replication';dest.mkdir(exist_ok=True)
    if not (dest/'prereg.json').exists():
        save('replication/prereg.json',dict(utc=now(),protocol=sha(D/'REPLICATION_RU.md'),
            source=sha(D/'replicate.py'),fetch=sha(D/'fetch_python_archive.py'),
            r4=sha(R/'models.pkl'),frozen=sha(D/'ablation_models.pkl'),full=sha(D/'models.pkl'),
            prior_results=sha(D/'results.json'),external_url=URL))
    reference={name:(sz,crc) for name,comp,sz,crc in load(R/'archive_members.json')}
    names={'cff':'first','cfr':'random'};metadata={}
    with zipfile.ZipFile(Remote()) as z:
        for short,tag in names.items():
            member='data/test/retrieval/python/cross_file_'+tag+'.gz'
            p=dest/(short+'.gz')
            if not p.exists():p.write_bytes(z.read(member))
            raw=p.read_bytes()
            assert (len(raw),zlib.crc32(raw))==reference[member]
            metadata[short]=dict(name=member,sha=sha(p),bytes=len(raw),crc32=reference[member][1])
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as f:obj=Restricted(f).load()
            for level,items in obj.items():
                panel=f'python_{short}_test_{level}';out=dest/(panel+'.parquet');writer=None
                for start in range(0,len(items),96):
                    batch=[dict(repo_name=r['repo_name'],code=r['code'],context=r['context'],
                        gold_snippet_index=r['gold_snippet_index'] if 'gold_snippet_index' in r else r['golden_snippet_index'])
                        for r in items[start:start+96]]
                    t=pa.Table.from_pylist(batch)
                    if writer is None:writer=pq.ParquetWriter(str(out),t.schema,compression='zstd')
                    writer.write_table(t)
                writer.close()
                metadata[panel]=dict(n=len(items),sha=sha(out))
            del obj
    save('replication/source.json',dict(utc=now(),members=metadata))
if __name__=='__main__':main()
