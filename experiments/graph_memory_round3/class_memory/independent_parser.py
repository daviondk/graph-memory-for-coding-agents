"""Attribute parse or allowlist rejections using the archived replies and a fixed taxonomy, with no program edits."""
import ast
import re
from collections import Counter
from independent_audit import get, matches, parse_candidate, write
from independent_sealed import clean_reply

def issue(raw,name):
    try:
        parse_candidate(raw,name)
        return None
    except SyntaxError as exc:
        return 'Python syntax: '+exc.msg
    except ValueError as exc:
        return str(exc)
    except TypeError as exc:
        return 'TypeError: '+str(exc)

def main():
    matches('online_decision_lock.json')
    cas=get('online_programs.json.gz')
    totals=Counter();uniq={};arms=Counter();examples={}
    for c in cas:
        for a,entries in c['logs'].items():
            for log in entries:
                rec=get('online_calls/'+log['key']+'.json.gz');err=issue(clean_reply(rec),log['name'])
                assert (err is None)==log['valid']
                if err:
                    meta=dict(reason=err,finish_reason=rec['reply']['choices'][0]['finish_reason'],target=c['id']+'/'+log['name'])
                    uniq[log['key']]=meta;totals[err]+=1;arms[a]+=1
    write('independent_online_parse.json',dict(counts_logical=totals,counts_by_policy=arms,counts_unique=Counter(r['reason'] for r in uniq.values()),unique=uniq))


if __name__=='__main__':main()

