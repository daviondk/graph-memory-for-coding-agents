"""Make a small machine-readable index from completed result artifacts."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def main():
    sets={
        'anchor_retention':['compact/results.json','compact/e3_results.json','compact/path_control/results.json'],
        'historical_actions':['procedure/results.json','procedure/verification/results.json','procedure/cost/results.json'],
        'invalidation':['validity/results.json','validity/external_validation/results.json','validity/age/results.json','validity/environment/results.json'],
        'repair':['repair/results.json','repair/generalization/results.json'],
        'interactive':['alfworld/results.json','alfworld/transfer_results.json','alfworld/transfer_strata.json','alfworld/text_only/results.json'],
        'negative_actions':['alfworld/text_only/failure_memory/results.json','procedure/failure_replay/results.json'],
        'resources':['runtime/verified.json','upstream/sources.json']}
    contents={}
    for group,files in sets.items():
        contents[group]=[]
        for file in files:
            p=ROOT/file;data=p.read_bytes();json.loads(data)
            contents[group].append({'file':file,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)})
    (ROOT/'RESULTS_INDEX.json').write_text(json.dumps(contents,indent=1))
if __name__=='__main__':main()
