import concurrent.futures,json,urllib.request,hashlib
from pathlib import Path
P=Path(__file__).resolve().parent/'upstream';P.mkdir(exist_ok=True)
repos={'snap-research/locomo':('3eb6f2c585f5e1699204e3c3bdf7adc5c28cb376',['data/locomo10.json','LICENSE.txt','README.MD']),
       'tomdif/memoria':('c8aa8194216652e41b9ff1272eac19943e2c784c',['benchmarks/locomo_bench.py','benchmarks/retrieval_metrics.py','benchmarks/results/2026-10-25/locomo_memoria_windowed.json','benchmarks/results/2026-10-25/locomo_flat_bm25.json','benchmarks/results/2026-10-25/locomo_minilm.json','memoria/retriever.py']),
       'campaign-layer/memory-core':('ffb105ee2c1c88609ad63f82c74082a8482e9ead',['bench/locomo/results/mode_a.json']),
       'thomasfevre/agent-memory-bench':('6cedf162c6e145ae5be8e6dcd642c6a9f2a26e64',['src/locomo_granularity.py','src/locomo_window_grid.py','src/locomo_predicted_router.py'])}
def get(args):
    repo,commit,path=args;url='https://raw.githubusercontent.com/'+repo+'/'+commit+'/'+path
    with urllib.request.urlopen(url,timeout=40) as f: data=f.read()
    (P/Path(path).name).write_bytes(data)
    return {'url':url,'file':Path(path).name,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
with concurrent.futures.ThreadPoolExecutor(6) as ex:rs=list(ex.map(get,[(repo,c,p) for repo,(c,ps) in repos.items() for p in ps]))
(P/'sources.json').write_text(json.dumps(rs,indent=2),encoding='utf8')
