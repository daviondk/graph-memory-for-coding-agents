"""Offline SHA-256 digest inventory of the stored primary and secondary evidence."""
from pathlib import Path
import hashlib,json,sys
root=Path(__file__).resolve().parent
dest=root/'MANIFEST.sha256.json'
def inventory():
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*'))
            if p.is_file() and p!=dest and '__pycache__' not in p.parts}
if __name__=='__main__':
    data=inventory()
    if '--check' in sys.argv:
        assert data==json.loads(dest.read_text(encoding='utf8')), 'Inventory differs from sealed files'
        print('Evidence manifest verified:',len(data),'files')
    else:
        dest.write_text(json.dumps(data,indent=1,ensure_ascii=True),encoding='utf8')
        print('Sealed',len(data),'files')

