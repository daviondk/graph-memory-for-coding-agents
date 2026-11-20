"""Online branch only. Teacher call directory and grades are never opened by this script."""
from independent_audit import get, matches, write
from independent_sealed import ONLINE, online_replay


if __name__=='__main__':
    checks=matches(ONLINE)
    source={c['task_id']:c for c in get('ClassEval_data.json')}
    data=online_replay(source)
    write('independent_online.json',{'online_seal_hashes':checks,**data})
    print('replayed online suites:',data['suites_reexecuted'])

