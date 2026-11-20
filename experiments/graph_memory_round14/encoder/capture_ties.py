"""A small input-only projection for auditing deterministic tie breaks offline."""
from forecast import D, PANELS, read, save, digest
def main():
    result={}
    for p,d in PANELS.items():
        assert digest(d/'inputs.json.gz')==read(d/'forecast.lock.json')['files']['inputs.json.gz']
        result[p]={r['id']:sorted(r['docs'],key=lambda name:(-r['docs'][name]['last'],name)) for r in read(d/'inputs.json.gz')}
    save(D/'tie_order.json.gz',result)
if __name__=='__main__':main()
