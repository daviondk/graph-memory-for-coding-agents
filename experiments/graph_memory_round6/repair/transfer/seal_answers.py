"""Seal all uniquely assigned and returned model requests before grading."""
import gzip
import hashlib
import json
from driver import D,lock,read


if __name__=='__main__':
    assert not (D/'gpu_answer_lock.json').exists()
    ids=read(D/'assign.json')
    keys={k for arms in ids.values() for k in arms.values()}
    files=sorted((D/'calls').glob('*.json.gz'))
    assert {f.name.split('.')[0] for f in files}==keys
    for f in files:
        data=json.loads(gzip.decompress(f.read_bytes()))
        packet=json.dumps(data['request'],sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()
        assert hashlib.sha256(packet).hexdigest()==f.name.split('.')[0] and data['response']['choices']
    lock('gpu_answer_lock.json',[*files,D/'assign.json',D/'input_lock.json',D/'packet_lock.json',D/'launch.json'])
