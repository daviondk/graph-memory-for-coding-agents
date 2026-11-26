from pathlib import Path
import json
s = json.loads((Path(__file__).resolve().parent/'source-check.json').read_text('utf8'))
assert len(s['required']) == 3 and set(s['required']) == set(s['matches'])
assert all(not values for values in s['matches'].values())
assert s['remote_files'] == 280 and s['tracked_files'] == 273
assert all(len(x) == 40 for x in (s['checkout'], s['remote_commit'], s['remote_tree']))
assert len(s['huggingface']) == 2
print('Checked both releases, three required filenames, inventories for Git and Hugging Face.' if s['checked_github_releases'] else 'Three required filenames absent in the pinned Git and Hugging Face inventories. No GitHub releases listed.')
