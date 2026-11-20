"""Audit positives for edits to held-out test files, without disclosing those paths."""
import argparse
import hashlib
import json
from pathlib import Path
from statistics import mean
from grade import ARMS, DATA, HERE, ROOT, TARGETS, read, save, sha


def paths(patch):
    out = set()
    for line in patch.splitlines():
        if not line.startswith('diff --git '):
            continue
        # SWE-ContextBench's four pinned Python instances use simple git paths.
        # Stop on a quoted or ambiguous path so a protected test cannot be missed.
        pair = line.removeprefix('diff --git ').split(' ')
        if len(pair) != 2 or not pair[0].startswith('a/') or not pair[1].startswith('b/'):
            raise ValueError('Unsupported git path quoting in protected-file audit')
        out.update([pair[0][2:], pair[1][2:]])
    if patch.strip() and not out:
        raise ValueError('Nonempty patch lacks verifiable diff headers')
    return out


def audit(data):
    rows=[]
    grouped = {}
    receipts = []
    for iid in TARGETS:
        case = read(data/'case_metadata'/(iid+'.json'))
        protected = paths(case['test_patch'])
        assert protected
        target = case['repo'] + '#' + str(case['pull_number'])
        signature = [case['base_commit']] + [hashlib.sha256(case[key].encode()).hexdigest()
                                              for key in ('patch','test_patch')]
        group = grouped.setdefault(target, {'verification_sha256':signature,'instances':[],'arms':{}})
        assert group['verification_sha256'] == signature
        group['instances'].append(iid)
        for arm in ARMS:
            r = read(HERE/'receipts'/iid/(arm+'.json'))
            f = ROOT/'runs'/iid/arm/'candidate.patch'
            assert r['input_patch_sha256'] == sha(f)
            solver = read(f.parent/'complete.json')
            assert solver['id'] == iid and solver['arm'] == arm and solver['patch_sha256'] == sha(f)
            candidate = paths(f.read_text(encoding='utf8'))
            overlap = candidate & protected
            rows.append({'instance_id':iid,'arm':arm,'candidate_sha256':sha(f),'candidate_files':len(candidate),
                         'official_test_files':len(protected),'overlapping_files':len(overlap),'resolved':r['resolved']})
            group['arms'].setdefault(arm,[]).append(int(r['resolved']))
            keys=('calls','input_tokens','output_tokens','record_available','evidence_shown','read_requests',
                  'elapsed_s','finish_reason','patch_bytes')
            receipts.append({'instance_id':iid,'pull_request':target,'arm':arm,'resolved':r['resolved'],
                             'test_status_present':r['tests_status_present'],**{k:solver[k] for k in keys}})
    metrics={}
    for arm in ARMS:
        trials=[x for x in receipts if x['arm']==arm]
        metrics[arm]={'issue_rate':mean(x['resolved'] for x in trials),
                      'mean_within_pr_then_across_pr':mean(mean(group['arms'][arm]) for group in grouped.values()),
                      **{k:sum(x[k] for x in trials) for k in ('calls','input_tokens','output_tokens','record_available',
                                                                 'evidence_shown','read_requests','test_status_present')}}
    matched={'unique_prs':len(grouped),'paired_issue_wordings':len(TARGETS),'groups':grouped,'metrics':metrics,'trials':receipts}
    path_check={'checked':len(rows),'accepted_with_overlap':sum(r['resolved'] and r['overlapping_files']>0 for r in rows),
                'rows':rows}
    return path_check,matched


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--data',type=Path,default=DATA)
    args=parser.parse_args()
    result,matched=audit(args.data)
    save(HERE/'test_path_audit.json',result)
    save(HERE/'matched_groups.json',matched)
    print(json.dumps({k:v for k,v in result.items() if k!='rows'}))

