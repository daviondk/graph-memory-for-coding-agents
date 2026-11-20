from pathlib import Path
import hashlib,json,shutil
root=Path(__file__).resolve().parent
out=root.parents[2]/'outputs'
q=json.loads((root/'final/qa.json').read_bytes())
assert q['raster_count']==15 and all(x['bounds_ok'] and len(x['titles'])==1 for x in q['pages'])
assert all(130<x['words']<500 and x['body_bottom_pt']<790 for x in q['pages'])
hashes={}
for ext in ('docx','pdf'):
    f=root/'final'/('agent-memory-session5-results.'+ext)
    dst=out/f.name
    shutil.copy2(f,dst)
    digest=hashlib.sha256(dst.read_bytes()).hexdigest()
    assert digest==hashlib.sha256(f.read_bytes()).hexdigest()
    hashes[f.name]={'sha256':digest,'size':dst.stat().st_size}
(root/'final/published.json').write_text(json.dumps({'outputs':hashes,'pages':15,'all_pages_inspected':True},indent=2),encoding='utf8')
print(hashes)
