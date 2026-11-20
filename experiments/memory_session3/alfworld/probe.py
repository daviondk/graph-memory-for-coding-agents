from engine import *
for kind in ('pick_and_place_simple','look_at_obj_in_light','pick_clean_then_place','pick_heat_then_place','pick_cool_then_place','pick_two_obj'):
    game=next(g for g in sorted((DATA/'train').glob(kind+'*/*/game.tw-pddl')) if json.loads(g.read_bytes()).get('solvable'))
    env=create(game);s=env.reset();print(s.feedback);print(s.admissible_commands[:16])
    for i in range(3):
        cmds=s.admissible_commands
        action=next((c for c in cmds if c.startswith('open ')),next(c for c in cmds if c.startswith('go to ')))
        s,_,_=env.step(action); print(action,repr(s.feedback),[c for c in s.admissible_commands if not c.startswith('go to ')][:18])
    env.close()

