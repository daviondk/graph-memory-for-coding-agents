"""Equal codec choice on compressed full counts and buffered frontiers."""
import argparse
from collections import Counter
from time import perf_counter_ns
import zlib

from cache import ExactCache, HERE
from measure_incremental import evaluate, save, load
from transfer import run

MODES=("all","bound16")


class CompressedCache(ExactCache):
    counters=Counter()

    def encode(self, packet):
        start=perf_counter_ns()
        compressed=zlib.compress(packet, level=1)
        use=len(compressed)<len(packet)
        result=bytes([int(use)])+(compressed if use else packet)
        end=perf_counter_ns()
        self.counters["encode_calls"]+=1
        self.counters["zlib_selected"]+=int(use)
        self.counters["source_bytes"]+=len(packet)
        self.counters["tagged_bytes"]+=len(result)
        self.counters["encode_ns"]+=end-start
        return result

    def decode(self, packet):
        start=perf_counter_ns()
        result=zlib.decompress(packet[1:]) if packet[0] else packet[1:]
        self.counters["decode_ns"]+=perf_counter_ns()-start
        self.counters["decode_calls"]+=1
        return result


if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--verify",action="store_true")
    args=ap.parse_args()
    original,a=evaluate(modes=MODES,factory=CompressedCache)
    extra,b=run(MODES,CompressedCache)
    counters=dict(CompressedCache.counters)
    times={k:counters.pop(k) for k in ("encode_ns","decode_ns")}
    for name,obj in (("codec-queries.json.gz",original+extra),
                     ("codec-results.json",dict(original=a,transfer=b,operations=counters))):
        if args.verify:
            assert obj==load(HERE/name)
        else:
            save(HERE/name,obj)
    if not args.verify:
        save(HERE/"codec-timing.json",times)
    for key,group in (("original",a),*b["panels"].items()):
        print(key, [(p,{m:v["bytes"] for m,v in plans.items()}) for p,plans in group.items()])
    print(counters,times)
