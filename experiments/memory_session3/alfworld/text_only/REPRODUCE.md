# ALFWorld without the admissible-command menu

All artifacts for this extension live in text_only. The standalone, offline audit is `python audit.py --check` from this folder after the evaluator finishes. It requires only Python's standard library. It replays 39 training scouts, reproduces the learned frequency table, then feeds each actor only its own visible feedback in order to regenerate every selected action in all 134 × 5 scheduled unseen runs. It compares stored successful environment outcomes and paired metrics. Auditing recorded rewards checks their consistency; independently proving a simulation reward requires rerunning the actual environment.

For a physical rerun, use a new directory in the same tree as the existing ALFWorld study, containing the source files and frozen roster. Provide the parent engine.py, the official ALFWorld source, deterministic demangler, pinned TextWorld environment and the released game data at the paths expected by engine.py. The study container has these under /study and the original experiment records dependencies in ../pip_freeze.txt and ../image_digest.txt. The runner requests `textworld.EnvInfos(won=True)` and never requests admissible commands. Input to the policy constructor is the reset text, arm and training table. State updates consume only the issued action and public feedback. The environment driver uses terminal/win signals only to stop and evaluate. Identifiers and family labels stay in the outer evaluator.

Commands inside that environment, in order:

```
python run.py train
python run.py learn
python run.py dev
python run.py seal
python run.py eval
python audit.py
python audit.py --check
```

Runner uses two workers; each worker executes all arms for its assigned episode and writes its final compressed records atomically. Existing files are resumed. Replay from scratch in a separate writable copy without train, dev, eval or derived outcomes. The native reward/done flags, action, resulting feedback, parser confirmation status and per-arm retained-entry count are logged in each step. Each training scout traverses the public location list in fixed order, opens visibly closed containers, and counts object kinds once per successfully inspected location. The ranker uses raw sighting counts; popular location kinds have more chances to contribute.

`pose_cycle` uses the current shared pose and a fixed order to choose the next visible place. Its search memory always has zero entries. `none` makes the same location ordering available, chooses the first place distinct from the current one, and can revisit the same two places. Both retain the operational state needed to act (visible room locations, current pose and local objects, held and delivered items, processing stage). Neither is a stateless policy in the absolute sense. `cursor` records the last searched place in each phase. `full` records visited places of the phase. `trained` adds the training-only target ordering to full. Every action, including stalled/unsuccessful ones, counts toward the limit of 50.
