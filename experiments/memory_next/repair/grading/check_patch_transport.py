"""Exercise persisted writes through the primary solver's frozen Docker entry points."""
import hashlib
import json
import sys
from pathlib import Path
from grade import HERE, ROOT, read, save, stamp
sys.path.insert(0,str(ROOT))
import workspace


def run():
    source=read(ROOT/'public_tasks.json')[0]
    proof=read(ROOT/'images.json')[source['id']]
    cid=workspace.create(source,proof)
    try:
        assert workspace.patch(cid)==b''
        initial=workspace.shell(cid, "printf 'initial\\n' > diagnostic-tracked.txt && git add diagnostic-tracked.txt && git -c user.name=diagnostic -c user.email=diagnostic@localhost commit -qm diagnostic")
        initial.check_returncode()
        edited=workspace.shell(cid, "printf 'changed\\n' > diagnostic-tracked.txt && printf 'new\\n' > diagnostic-new.txt")
        edited.check_returncode()
        observed=workspace.shell(cid,'cat diagnostic-tracked.txt diagnostic-new.txt')
        assert observed.stdout==b'changed\nnew\n' and observed.returncode==0
        patch=workspace.patch(cid)
        assert all(b in patch for b in (b'--- a/diagnostic-tracked.txt',b'+changed\n',b'-initial\n',b'--- /dev/null',b'+++ b/diagnostic-new.txt',b'+new\n'))
        assert workspace.patch(cid)==patch
        path=HERE/'patch_transport.json'
        save(path,{'environment':source['id'],'image':proof['image_id'],'container':cid,'utc':stamp(),'tracked_and_new_file_visible':True,'calls':'distinct shell invocations plus two patch invocations','patch_bytes':len(patch),'sha256':hashlib.sha256(patch).hexdigest(),'workspace_py_sha256':hashlib.sha256((ROOT/'workspace.py').read_bytes()).hexdigest()})
        print('Transport OK, bytes',len(patch),flush=True)
    finally:
        workspace.docker(['rm','-f',cid])


if __name__=='__main__':run()
