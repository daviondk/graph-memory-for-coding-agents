"""Render concise numerical fields used to transcribe the human report."""
from study import ROOT, read, ARMS
def main():
    r=read(ROOT/'results.json'); diag=read(ROOT/'diagnostics.json'); total=r['coverage']['selected']
    print('flow',read(ROOT/'flow.json'),'coverage',r['coverage'])
    for key,vals in r['arms'].items():
        print(key, vals['patch_menu_hit'],vals['patch_read_hit'],vals['available'],vals['read_lines'],[round(vals[m],4) for m in ('precision','recall','f1_score')])
    print('contrasts',{k:(v['all'],v['primary_discordant']) for k,v in r['contrasts'].items()})
    print('diagnostics',{k:v['counts'] for k,v in diag['arms'].items()},'changed',len(diag['scope_lexical_changed']),'invalid',len(diag['invalid_native']))
    print('cost',r['costs'])
if __name__=='__main__':main()
