"""Prepare the external cohort. The four signature policies are byte-identical to the first panel."""
from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parent;P=R.parent
for n in ['scope.py','predict.py','run_observations.py','score.py','testmon_pair.py','economics.py']:
    (R/n).write_bytes((P/n).read_bytes())
obs=(P/'observe.py').read_text(encoding='utf8')
old="if r['format']=='str':v=str(v)"
new=old+'''
        if r['format']=='pattern':
            rx=getattr(v,'regex',None)
            v=[getattr(rx,'pattern',None),getattr(v,'include',None)]
        if r['format']=='plain' and isinstance(v,dict):
            # Canonicalize date/time leaves across Python processes.
            v={k:(q.isoformat() if callable(getattr(q,'isoformat',None)) else q) for k,q in v.items()}'''
(R/'observe.py').write_text(obs.replace(old,new),encoding='utf8')
src=(P/'sources.py').read_text(encoding='utf8');l=src.index('VERS=');r=src.index('\ndef sha',l)
src=src[:l]+"VERS={'tomli':'1.2.3 2.0.1 2.0.2 2.2.1 2.3.0','pathspec':'0.8.1 0.9.0 0.10.3 0.11.2 0.12.1','humanize':'3.13.1 4.0.0 4.5.0 4.8.0 4.11.0'}"+src[r:]
src=src.replace("if name.startswith(pkg+'/') and name.endswith('.py'):","if (name.startswith(pkg+'/') and name.endswith('.py')) or name.endswith('.dist-info/METADATA'):")
(R/'sources.py').write_text(src,encoding='utf8')
assert (R/'scope.py').read_bytes()==(P/'scope.py').read_bytes()

