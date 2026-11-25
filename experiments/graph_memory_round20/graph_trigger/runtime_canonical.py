"""Expose the full native checkpoint in the immutable CPU runtime probe's file schema."""
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch
import runtime_probe as rt

graph=rt.GRAPH
g=rt.gate
src=g.load(graph/'forecast-seal.json')
ck=g.load(graph/'checkpoint.json')
parent=rt.RUN/'runtime-adapters';parent.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(dir=parent) as temp:
    private=Path(temp)
    base=private/'cpu_fallback/canonical'
    base.mkdir(parents=True)
    ref=graph/'best.pt'
    assert g.sha(ref)==ck['sha']
    for name in ['best.pt','checkpoint.json',*[k for k in src['forecasts'] if k.startswith('forecasts-rgcn-')]]:
        os.link(graph/name,base/name)
    copied={k:src['forecasts'][k] for k in src['forecasts'] if k.startswith('forecasts-rgcn-')}
    assert len(copied)==8 and all(g.sha(base/k)==v for k,v in copied.items())
    (base/'forecast-seal.json').write_text(json.dumps({'files':copied},sort_keys=True),encoding='utf8')
    with patch.object(rt,'GRAPH',private):rt.measure('canonical')
    g.put(rt.ROOT/'canonical-runtime-source.json',dict(original_forecast_sha=g.sha(graph/'forecast-seal.json'),
          checkpoint_sha=ck['sha'],consumed_ranks=copied,adapter=g.sha(Path(__file__))))
