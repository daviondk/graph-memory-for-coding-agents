"""Synthetic fixture only. Does not touch the real three actor workspaces."""
from pathlib import Path
from tempfile import TemporaryDirectory
import gateway as g
from settings import dump
def main():
    with TemporaryDirectory() as tmp:
        root=Path(tmp);folder=root/'actor';folder.mkdir();g.B=root/'base';g.ISSUE=root/'issue'
        g.ISSUE.write_text('synthetic',encoding='utf8');(folder/'memory.txt').write_bytes(b'abc')
        for p in (g.B,folder/'checkout'):
            f=p/'src/click/core.py';f.parent.mkdir(parents=True);f.write_bytes('def x():\r\n    return 4\r\n'.encode())
        dump(folder/'session.json',dict(started=False,counts={},bytes=0,edits={},logs=[],frozen=None))
        call=lambda **p:g.dispatch(folder,p)
        assert call(op='list')[0]==400
        assert call(op='start')[1]['memory_bytes']==3
        assert call(op='read',path='../issue',start=1,end=1)[0]==400
        assert call(op='list')[1]['files']==['src/click/core.py']
        p=dict(op='read',path='src/click/core.py',start=1,end=2,request_id='r1')
        a=call(**p);assert a==call(**p) and a[1]['charged_bytes']==22
        assert call(op='edit',path='src/click/core.py',old='def x():\n    return 4',new='def x():\n    return 5')[0]==200
        assert (folder/'checkout/src/click/core.py').read_bytes().endswith(b'5\r\n')
        assert 'return 5' in call(op='search',literal='return',path='src/click/core.py')[1]['text']
        result=call(op='finish')[1];assert result['files']==['src/click/core.py'] and result==call(op='finish')[1]
        assert b'+    return 5' in (folder/'change.patch').read_bytes()
        assert call(op='edit',path='src/click/core.py',old='5',new='6')[0]==400
        assert (g.B/'src/click/core.py').read_bytes().endswith(b'4\r\n')
    print('Synthetic gateway checks passed')
if __name__=='__main__':main()
