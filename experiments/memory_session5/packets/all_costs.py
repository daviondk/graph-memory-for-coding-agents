"""Sum the exact serialized packet costs across every boundary, including no later accepted edit."""
from collections import Counter,defaultdict
import json,sys
from common import ROOT,rows
def main():
    report={}
    for n,f in [('A',ROOT),('B',ROOT/'transfer/test')]:
        count=0;totals=defaultdict(Counter)
        for k in range(8):
            for iid,t,budgets in rows(f/'sealed'/f'{k}.jsonl.gz'):
                count+=1
                for b,arms in budgets.items():
                    for name,(ids,cost) in arms.items():totals[b][name]+=cost
        report[n]={'all_cuts':count,'costs':{b:{a:{'sum_tokens':v,'mean':v/count} for a,v in rs.items()} for b,rs in totals.items()}}
    if '--write-report' in sys.argv:(ROOT/'all_cut_costs.json').write_text(json.dumps(report,indent=1))
    else:assert json.loads((ROOT/'all_cut_costs.json').read_bytes())==report
    print('PASS')
    for n,res in report.items():
        for b,vs in res['costs'].items():
            arm='reset_tail' if b=='256' else 'rebased_tail';print(n,b,'joint',vs['joint'],'control',arm,vs[arm])
if __name__=='__main__':main()
