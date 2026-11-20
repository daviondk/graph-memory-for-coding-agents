"""Matched information counterexample in inert text-only directories."""
import shutil,subprocess,time
from common13 import D,sha,dump
from forecast13 import normalized,contains,inside
def main():
    rows=[]
    for trial in range(12):
        code=sha(f'twin|{trial}'.encode())[:12];needle='absent_marker_'+code
        lines=[f'def ordinary_helper_{n}_{code}(parameter_one, parameter_two):' for n in range(4)]
        for mode in ['sibling','hidden_suffix','visible']:
            for pos in [False,True]:
                path=D/'controlled'/code/mode/('present' if pos else 'absent');path.mkdir(parents=True,exist_ok=True)
                tail=needle if pos and mode in ['hidden_suffix','visible'] else 'ordinary_return_value'
                first='\n'.join(lines+[tail])+'\n';second=(needle if pos and mode=='sibling' else 'ordinary_sibling_value')+'\n'
                (path/'viewed.txt').write_text(first,encoding='utf8');(path/'sibling.txt').write_text(second,encoding='utf8')
                shown='\n'.join(lines+([tail] if mode=='visible' else []));shown_lines=normalized(shown)
                actual={l.strip() for l in first.splitlines() if len(l.strip())>=20};matches=shown_lines&actual
                key=dict(scope='.',globs=[],literal=needle,oi=False,word=False)
                red=any(contains(l,key) for l in matches)
                features=dict(directory=('sibling.txt','viewed.txt','readme.txt'),long_lines=len(matches),line_hashes=sorted(sha(l.encode()) for l in matches),scope=inside('viewed.txt',key),prior_positive=red)
                (path/'readme.txt').write_text('Names in the directory are identical.\n',encoding='utf8')
                t0=time.perf_counter_ns();cmd=['git','-C',str(path),'grep','--no-index','-q','-F','-e',needle,'--','.']
                rc=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE).returncode;dt=time.perf_counter_ns()-t0;assert rc in [0,1] and (rc==0)==pos
                rows.append(dict(trial=trial,kind=mode,condition='present' if pos else 'absent',features=features,git_return=rc,paid_lookup_ns=dt,input_files={f.name:sha(f.read_bytes()) for f in path.glob('*.txt')}))
    for i in range(0,len(rows),2):
        a,b=rows[i:i+2];assert a['git_return']!=b['git_return']
        if a['kind']!='visible':assert a['features']==b['features']
        else:assert not a['features']['prior_positive'] and b['features']['prior_positive']
    dump(D/'controlled_results.json',dict(pairs=len(rows)//2,equal_prefix_different_truth=24,visible_positive_controls=12,records=rows))
if __name__=='__main__':main()