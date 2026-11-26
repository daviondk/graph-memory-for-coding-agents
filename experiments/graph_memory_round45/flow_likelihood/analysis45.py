from common45 import *
import importlib.util
spec=importlib.util.spec_from_file_location('r43_boot',R43/'analysis.py')
study=importlib.util.module_from_spec(spec);spec.loader.exec_module(study)

def main(stage):
    receipt=read(D/f'{stage}-grade.json')
    assert sha(D/f'{stage}-outcomes.json.gz')==receipt['outcomes']
    raw=read(D/f'{stage}-outcomes.json.gz')
    pairs=[('table','rich'),('table','bit'),('table','native'),('bit','rich'),('bit','native')]
    sets={'primary':[r for r in raw if r['fired'] and r['eligible'] and not r['pilot']],
          'nonpilot':[r for r in raw if not r['pilot']],'all':raw}
    if stage=='trigger':sets['fired']=[r for r in raw if r['fired']]
    groups={k:study.analyze([(r['q'],r['t'],r['arms']) for r in rows],pairs) for k,rows in sets.items()}
    assert len(sets['primary'])=={'mid':901,'trigger':649}[stage] and len(raw)==2000
    res=dict(groups=groups,bootstrap=10000,seed=430313,metrics=['FS','coverage','tokens'],grade=sha(D/f'{stage}-grade.json'))
    save(D/f'{stage}-results.json',res)
    r=groups['primary'];print(stage,r['mu'])
    for z in r['comparisons']:print(z['left'],z['right'],z['delta'][0],z['interval'][0],z['wins'],z['losses'])

if __name__=='__main__':main(sys.argv[1])
