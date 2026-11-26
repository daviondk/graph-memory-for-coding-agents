"""Compare every single hit against upstream C, before observing the benchmark."""
from pathlib import Path
from hashlib import sha256
import json, os, random, subprocess
from policies import S3FIFO, Sieve
D = Path(__file__).resolve().parent


def main():
    rng = random.Random(491902)
    cases = [list(range(240)), list(range(45)) * 12, list(range(28)) * 45,
             list(range(31)) * 4 + list(range(38)) * 10]
    for alphabet in (17, 35, 70, 150):
        cases.append([rng.randrange(alphabet) for _ in range(4300)])
    cases.append([k for i in range(50) for k in list(range(45)) + [i % 9] * 7])
    tape = ' '.join(' '.join(map(str, [-1] + seq)) for seq in cases).encode()
    prefix = ['wsl', '-d', 'CodexX20MSR', '--'] if os.name == 'nt' else []
    data = {}
    for method, cls in [('s3',S3FIFO), ('sieve',Sieve)]:
        ref = subprocess.check_output(prefix + [os.environ.get('TARGET','/tmp/r49cache-reference'), method], input=tape).strip()
        expected = bytearray()
        for seq in cases:
            c = cls()
            expected.extend(49 if c.access(k) else 48 for k in seq)
        assert ref == expected, (method, next((i for i,(a,b) in enumerate(zip(ref, expected)) if a != b),None))
        data[method] = dict(hits=ref.count(b'1'), misses=ref.count(b'0'), bit_sha256=sha256(ref).hexdigest())
    output = dict(commit='5fa68ef6902350aa9734398862bec7912d59f5e3',
        S3FIFO_c='ce2f96a57d5015f734fbc3223003df323ca957a9177d1e5e4f711240d227553e',
        Sieve_c='45bec63a08c8f1951cfcb369f35df0521bf79906b72976825a4e1f8c851f9b05',
        traces=len(cases), requests=sum(map(len,cases)), trace_sha256=sha256(tape).hexdigest(), arms=data)
    (D/'reference.json').write_text(json.dumps(output,indent=2)+'\n',encoding='utf-8')
    print(output['requests'],data)


if __name__ == '__main__': main()

