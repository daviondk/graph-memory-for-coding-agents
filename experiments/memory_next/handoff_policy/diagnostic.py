"""Post hoc: characterize the registered recipient-only baseline against full trajectories."""
from score import *
def main():
    design={key(x):x for x in csvrows(ART/'assignments.csv')};outcomes={r['run_id']:r for r in csvrows(ART/'arm_outcomes.csv')}
    steps=[(p,{a:outcomes[design[key(p)][a]] for a in ARMS}) for p in read('decisions.json')]
    output={'status':'diagnostic after primary result','recipient_vs_raw':compare(steps,'recipient','raw_trace'),'by_recipient':{}}
    for name in sorted({p['succ'] for p,y in steps}):
        subset=[(p,y) for p,y in steps if p['succ']==name]
        output['by_recipient'][name]={'n':len(subset),'formats':dict(Counter(p['recipient'] for p,y in subset)),'vs_raw':compare(subset,'recipient','raw_trace')}
    dump('recipient_diagnostic.json',output)
    print(output['recipient_vs_raw'])
if __name__=='__main__':main()

