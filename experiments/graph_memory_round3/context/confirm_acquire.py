"""Unlabeled external replication cohort, with independently registered project names and cap."""
from pathlib import Path
import json
import acquire as a
D=Path(__file__).resolve().parent
REPOS=set("""conan-io__conan iterative__dvc python-trio__trio burnash__gspread marshmallow-code__webargs pndurette__gTTS john-kurkowski__tldextract theskumar__python-dotenv pallets__jinja aio-libs__async-timeout python-hyper__h11 cloudpipe__cloudpickle""".split())
if __name__=="__main__":
    assert not (REPOS & a.SAFE) and not (REPOS & a.ALLOWED)
    H=D/"replication";H.mkdir(exist_ok=True)
    import inspect
    code=inspect.getsource(a.main).replace('co[repo]<48','co[repo]<32').replace('r3edge','r3replica').replace('H/"acquire.py",H/"PROTOCOL_RU.md"','D/"confirm_acquire.py",D/"EXPANSION_PROTOCOL.md"')
    ns={**a.__dict__,"H":H,"D":D,"SAFE":REPOS}
    exec(compile(code,"replication_acquire","exec"),ns);ns["main"]()
    selected=json.loads((H/"selection.json").read_bytes());primary=json.loads((D/"selection.json").read_bytes())
    assert not ({i for i,*_ in selected}&{i for i,*_ in primary})

