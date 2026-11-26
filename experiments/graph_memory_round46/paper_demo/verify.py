"""Check the distributable contents and the manuscript-to-demo linkage."""
from pathlib import Path
from zipfile import ZipFile
from hashlib import sha256
import json
d=Path(__file__).resolve().parent
receipt=json.loads((d/'CONTENT_SHA256.json').read_bytes())
with ZipFile(d/'candidate.zip') as z:
    assert z.testzip() is None and set(z.namelist())==set(receipt)|{'CONTENT_SHA256.json'}
    for n,h in receipt.items():
        assert sha256(z.read(n)).hexdigest()==h==sha256((d/n).read_bytes()).hexdigest()
clip=json.loads((d/'browser-video.json').read_bytes())
assert len(clip['scenes'])==9 and 'Exact match' in clip['scenes'][-1][1]
assert clip['seconds']==134.32 and clip['bytes']==(d/'walkthrough.mp4').stat().st_size
pool=d.parent/'trust_view/view.sqlite'
if pool.is_file():
    assert sha256(pool.read_bytes()).digest()==sha256((d/'apps/trace/runtime/view.sqlite').read_bytes()).digest()
print('Verified 34 archive members, source-weight database and nine recorded scenes.')
