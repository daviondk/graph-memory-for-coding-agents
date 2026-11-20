"""Compare two lookup keys on the frozen 64-trace audit. Python 3.10+, no network."""
from collections import defaultdict
from pathlib import Path
import json, re, shlex, sys
def run(data):
    by_key=defaultdict(set)
    exact=defaultdict(set)
    seen=set()
    events=0
    for trace in data['traces']:
        for event in trace['events']:
            cwd, cmd = event['cmd'].split(' :: ',1)
            argv=shlex.split(cmd)
            args=argv[argv.index('pytest')+1:]
            # Accept exactly one explicit .py target under test[s]/, before any test node suffix.
            # Exclude separately supplied option values and commands selecting multiple files.
            targets=[]
            skip=False
            for arg in args:
                if skip:
                    skip=False
                    continue
                if arg in ('-k','-m','--ignore','--deselect','-c','--rootdir','--confcutdir'):
                    skip=True
                    continue
                if re.fullmatch(r'(?:\./)?tests?/[^\s:]+\.py(?:::.+)?',arg):
                    targets.append(arg.split('::')[0].removeprefix('./'))
            if len(targets)==1:
                key=(trace['repo'],cwd,targets[0])
                by_key[key].add(trace['path'])
                exact[(trace['repo'],event['cmd'])].add(trace['path'])
                seen.add(trace['path'])
                events+=1
    repeated={k:v for k,v in by_key.items() if len(v)>1}
    return {'matching_events':events,'traces_with_key':len(seen),'unique_keys':len(by_key),
            'exact_unique_same_events':len(exact),'exact_repeated_same_events':sum(len(v)>1 for v in exact.values()),
            'exact_traces_with_repeated_key':len(set().union(*(v for v in exact.values() if len(v)>1))),
            'repeated_keys':len(repeated),'traces_with_repeated_key':len(set().union(*repeated.values())),
            'repeated':[{'repo':k[0],'cwd':k[1],'test_file':k[2],'paths':sorted(v)} for k,v in sorted(repeated.items())]}
if __name__=='__main__':
    data=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'))
    print(json.dumps(run(data),indent=2))

