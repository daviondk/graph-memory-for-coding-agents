from score import build,compute,ROOT,save,csv
if __name__=='__main__':
    rows,dur,comparators=build(False)
    assert len(rows)==1428
    d=compute(rows,dur,comparators)
    for g in d['groups'].values():
        for m in ['testmon','testmon_normal']:del g[m]
    del d['comparators']
    save(ROOT/'results.json',d)
    with (ROOT/'per_check.csv').open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print(d['groups']['all'])

