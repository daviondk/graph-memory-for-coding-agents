"""Post-result diagnostic contrasts. No changes to frozen predictors or main results."""
import hashlib,json
from pathlib import Path
from aggregate import rows,contrast,stats
ROOT=Path(__file__).resolve().parent
def main():
    native=[r for r in rows(ROOT) if r['accepted']]
    tagged=[r for r in rows(ROOT/'tagged') if r['accepted']]
    out={'registered_after_results':True,'status':'exploratory descriptive contrasts',
         'budget':512,'denominator':'historically accepted next literal edit preconditions',
         'baseline_selection':'strongest observed no-update displayed-text arm at 512 tokens was drop_recenttail',
         'no_tuning':'All methods, inputs and predictions were already frozen. Contrasts were requested after main results were read.',
         'source_score_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                               for base in (ROOT,ROOT/'tagged') for p in sorted((base/'scores').glob('*.jsonl.gz'))},
         'cohorts':{}}
    for name,data in [('native',native),('tagged',tagged),('all',native+tagged)]:
        summary=stats(data)['512']
        out['cohorts'][name]={
            'n':len(data),
            'counts':{k:summary[k]['preimage'] for k in ('drop_mid','drop_recenttail','rebase_mid','drop_fused','rebase_fused')},
            'updated_center_minus_strongest_reset_tail':contrast(data,'rebase_mid','drop_recenttail'),
            'prespecified_updated_fused_minus_strongest_reset_tail':contrast(data,'rebase_fused','drop_recenttail')}
    out['interpretation']='Matched-reader improvement isolates the effect of updating for that reader. A comparison to the strongest observed no-update reader assesses competitiveness. These post-result contrasts have selection effects and do not establish SOTA or new-agent repair success.'
    (ROOT/'strong_control.json').write_text(json.dumps(out,indent=2),encoding='utf8')
    print(json.dumps(out['cohorts'],indent=2))
if __name__=='__main__':
    main()

