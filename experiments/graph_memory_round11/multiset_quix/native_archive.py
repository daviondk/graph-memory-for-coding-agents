"""Save all 36 primary files; materialize only into a separate new temporary dataset root."""
import argparse,base64,hashlib
from pathlib import Path
from qutil import Q,R9,load,put,sha
def main():
    p=argparse.ArgumentParser();p.add_argument('--export',action='store_true');p.add_argument('--unpack',type=Path);a=p.parse_args()
    refs=load(Q/'native_inputs.json')
    if a.export:
        files={k:base64.b64encode((R9/k).read_bytes()).decode() for k,h in refs.items()}
        assert all(sha(R9/k)==h for k,h in refs.items())
        put(Q/'native_source_and_traces.json.gz',files)
    if a.unpack:
        root=a.unpack.resolve()
        assert root.name=='graph_memory_round9'
        files=load(Q/'native_source_and_traces.json.gz')
        assert set(files)==set(refs)
        for key,enc in files.items():
            dest=(root/key.replace(chr(92),'/')).resolve()
            assert dest.is_relative_to(root)
            data=base64.b64decode(enc);assert hashlib.sha256(data).hexdigest()==refs[key]
            if dest.exists():
                assert dest.read_bytes()==data
                continue
            dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
if __name__=='__main__':main()