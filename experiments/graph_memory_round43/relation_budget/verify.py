from pathlib import Path
import json,gzip,hashlib,math
D=Path(__file__).resolve().parent
def read(path):
    b=(D/path).read_bytes()
    return json.loads(gzip.decompress(b) if str(path).endswith('.gz') else b)
def sha(name):return hashlib.sha256((D/name).read_bytes()).hexdigest()
def verify(rows,result):
    assert len(rows)==result['questions'] and len(set(t for q,t,z in rows))==result['trajectories']
    for method,average in result['mu'].items():
        for metric in range(3):
            mu=math.fsum(row[2][str(seed)][method][metric] for row in rows for seed in (13,17,29,37,41))/(5*len(rows))
            assert abs(average[metric]-mu)<1e-9
    for pair in result['comparisons']:
        a,b=pair['left'],pair['right']
        assert abs(result['mu'][a][0]-result['mu'][b][0]-pair['delta'][0])<1e-9
        wins=losses=0
        for q,t,z in rows:
            for d in z.values():
                wins+=d[a][0]>d[b][0];losses+=d[a][0]<d[b][0]
        assert (wins,losses)==(pair['wins'],pair['losses'])
def manifest():
    if (D/'manifest.json').exists():
        assert all(sha(f)==h for f,h in read('manifest.json')['files'].items())
if __name__=='__main__':
    manifest()
    pred=read('predictions.json');score=read('evaluation.json');r=read('outcomes.json.gz')
    assert sha('outcomes.json.gz')==score['outcomes'] and all(sha(f)==h for f,h in pred['files'].items())
    for panel,rows in [('available',[v for v in r if v['eligible'] and not v['pilot']]),('nonpilot',[v for v in r if not v['pilot']]),('all',r)]:
        verify([(v['q'],v['t'],v['arms']) for v in rows],read('results.json')['groups'][panel])
    print('Verified all seven methods and eleven contrasts on three panels')
