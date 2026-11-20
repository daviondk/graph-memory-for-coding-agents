"""Publish verified, user-facing documents and their audit receipt locally."""
import hashlib
import json
import shutil
from pathlib import Path

here=Path(__file__).resolve().parent
folder=here/'final'
name='graph-memory-research-round1'
out=here.parents[2]/'outputs'
qa=json.loads((folder/'qa.json').read_text('utf8'))
audit=json.loads((folder/'source-audit.json').read_text('utf8'))
assert len(qa['pages'])==18 and audit['result']=='passed'
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
published={}
for ext in ('docx','pdf'):
    p=folder/(name+'.'+ext); dst=out/p.name
    shutil.copyfile(p,dst)
    assert digest(p)==digest(dst)
    published[str(dst)]=digest(dst)
receipt={'files':published,'pages':len(qa['pages']),'external_links':len(qa['links']),'word_tables':audit['word_tables'],
         'matched_raw_result_tables':len(audit['raw_score_tables']),'render_quality_check':digest(folder/'qa.json'),
         'source_audit':digest(folder/'source-audit.json')}
(folder/'released.json').write_text(json.dumps(receipt,indent=2),encoding='utf8')
print(receipt)

