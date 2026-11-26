"""Seal all original receipts when the quiet server omits its optional offload banner."""
import argparse
from collections import Counter
from pathlib import Path
from run_gpu import RUN, EXE, CACHE, NAME, DIGEST, AD, R39, D, R48, util


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--log', type=Path, help='Original local server log for this campaign')
    args = parser.parse_args()
    panel = util.read(D / 'panel.json')
    progress = util.read(D / 'progress.json')
    if progress['chains'] != progress['total'] or progress['chains'] != len(panel['selected']):
        raise RuntimeError('Incomplete GPU run')
    logs = list(RUN.glob('gpu-*.log'))
    logfile = args.log or (logs[0] if len(logs) == 1 else None)
    if logfile is None or not logfile.is_file():
        raise RuntimeError('Pass --log pointing to the original local server log')
    if NAME.encode() not in logfile.read_bytes():
        raise RuntimeError('The original log must confirm the requested model')
    source = util.read(R48 / 'input-seal.json')
    expected = dict(panel=util.sha(D / 'panel.json'), protocol=panel['protocol'],
                    runner=util.sha(D / 'run_gpu.py'), pdh=util.sha(D / 'pdh.py'),
                    admission=util.sha(AD / 'admission.py'), gdsf=util.sha(AD / 'gdsf.py'),
                    qwen=util.sha(R39 / 'reference.py'), model=DIGEST, exe=util.sha(EXE),
                    namespace=source['namespace'])
    assert util.sha(CACHE / NAME) == DIGEST
    results, hashes, engines = {}, {}, Counter()
    count = 0
    for chain in panel['selected']:
        file = RUN / (chain['priority'] + '.json')
        rec = util.read(file)
        assert rec['sig'] == expected and rec['seq'] == chain['seq']
        assert set(rec['modes']) == set(chain['methods'])
        for arm, rows in rec['modes'].items():
            assert [row['q'] for row in rows] == chain['seq']
            for row in rows:
                cuda = {k:v for k,v in row['device_engines'].items() if 'cuda' in k.lower()}
                assert sum(cuda.values()) > 0 and row['compute_engine_s'] > 0
                engines.update(cuda)
                count += 1
        results[chain['repo']] = rec['modes']
        hashes[chain['repo']] = util.sha(file)
    assert count == 96
    util.put('raw-runs.json.gz', results)
    util.put('run-seal.json', dict(sig=expected, raw=util.sha(D/'raw-runs.json.gz'),
             receipts=hashes, warmup=None, log=util.sha(logfile), backend={
                 'evidence':'Measured process-specific WDDM CUDA engine on every request',
                 'engine_seconds':dict(engines), 'requests':count,
                 'offload_banner_in_log':False, 'model_log':NAME},
             elapsed_to_last_chain=progress['seconds'], postprocess=util.sha(Path(__file__))))
    print('Sealed 8 original receipts and 96 observed process-specific CUDA records.')


if __name__ == '__main__':
    main()

