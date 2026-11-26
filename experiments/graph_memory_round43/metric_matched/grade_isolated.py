"""Start the upstream ISETrace scorer with its own research module search path."""
import sys
from pathlib import Path
D=Path(__file__).resolve().parent
initial=sys.path.copy()
import evaluate
for name,module in list(sys.modules.items()):
    location=getattr(module,'__file__',None)
    if name!='evaluate' and location and evaluate.W in Path(location).resolve().parents:
        del sys.modules[name]
del sys.modules["evaluate"]
sys.path[:]=[p for p in initial if Path(p).resolve()!=D]
evaluate.grade()
