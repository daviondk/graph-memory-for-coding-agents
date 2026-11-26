"""Offline integrity check for the revised paper and its portable review bundle."""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile
root=Path(__file__).resolve().parent
checks=json.loads((root/'CONTENT_SHA256.json').read_text('utf8'))
with ZipFile(root/'candidate.zip') as bundle:
    assert set(bundle.namelist()) == set(checks)|{'CONTENT_SHA256.json'} and bundle.testzip() is None
    for name,reference in checks.items():
        assert reference==hashlib.sha256(bundle.read(name)).hexdigest()==hashlib.sha256((root/name).read_bytes()).hexdigest()
p=(root/'paper.tex').read_text('utf8')
assert 'one total order on tied complete packets' in p and '490 to 343' in p
assert (root/'walkthrough.mp4').stat().st_size==2419620
print('Checked 31 archive members and the two manuscript changes.')
