"""Validate all public-policy outcomes using the actual compiled C routines."""
import os, subprocess, hashlib
from experiment import D, panels, read, dump, scheduler, CLASSES


def main():
    prefix = ['wsl','-d','CodexX20MSR','--'] if os.name=='nt' else []
    totals={}
    for panel, rows in panels().items():
        actual = read(D/(panel+'-outcomes.json.gz'))
        result = {}
        for tag in ('s3','sieve'):
            tape, weights, spans = [], [], []
            offset = 0
            ids = {}
            for q, (_,_,_,pred) in rows.items():
                for mode,hot in [('batch',False),('batch',True),('stream',False),('stream_reverse',False)]:
                    c=CLASSES[tag]()
                    tape.append(-1)
                    mark = []
                    path = pred + [q]
                    for step,k in enumerate(path):
                        docs=rows[k][0]
                        order=list(docs)
                        if mode=='stream_reverse': order.reverse()
                        old=c.residents()
                        if mode=='batch' and step==len(path)-1:
                            for key in order:
                                idx=ids.setdefault(key,len(ids))
                                tape.append(-2-idx)
                                mark.append((offset,docs[key]))
                                offset+=1
                        for key in scheduler(order,docs,old,hot):
                            idx=ids.setdefault(key,len(ids))
                            tape.append(idx)
                            if mode!='batch' and step==len(path)-1: mark.append((offset,docs[key]))
                            offset+=1
                            c.access(key)
                    spans.append((mark,actual[q][mode][tag+('_costhot' if hot else '')]))
            data=(' '.join(map(str,tape))).encode()
            binary=subprocess.check_output(prefix+[os.environ.get('TARGET','/tmp/r49cache-reference'),tag],input=data).strip()
            assert len(binary)==offset
            for mark, expected in spans:
                retrieved=[n for i,n in mark if binary[i]==49]
                assert [len(retrieved),sum(retrieved)]==expected
            result[tag]=dict(states=len(rows),forecasts=len(spans),probes=offset,tape=hashlib.sha256(data).hexdigest(),answers=hashlib.sha256(binary).hexdigest())
        totals[panel]=result
    dump('native-validation.json',totals)
    print(totals)


if __name__=='__main__': main()

