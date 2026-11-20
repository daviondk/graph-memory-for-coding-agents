"""Estimate timing-robust subset and repeat outcomes from the sealed auxiliary tests."""
from common import ROOT, read, save
from grade import paired

def main():
    output = {}
    for name in ('','transfer'):
        folder = ROOT/name
        def get(filename):
            return read((folder/filename).relative_to(ROOT))
        rows = get('evalplus_rows.json.gz')
        cases = {(r['id'],r['arm']):r for r in rows}
        ids = get('roster.json')['ids']
        excluded = {r['id'] for r in rows if r['evalplus']['status']=='timeout'}
        keep = [i for i in ids if i not in excluded]
        proposed = [cases[i,'bundle']['plus_hit'] for i in keep]
        control = [cases[i,'center']['plus_hit'] for i in keep]
        output[name or 'primary'] = {'n':len(keep),'excluded':sorted(excluded),
            'bundle':sum(proposed),'center':sum(control),'paired':paired(proposed,control)}
    save('evalplus_timeout_sensitivity.json',output)
    print(output)

if __name__=='__main__':
    main()
