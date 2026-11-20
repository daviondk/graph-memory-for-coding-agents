# E3. Context-only falsification control
Registered 2026-11-17, after E1 and E2 outcomes, before inspecting current action_history control outcomes. This is explicitly a post-E1 control and not an independent confirmatory superiority test.

## Question
Does E1's editable-click pointer contain predictive information beyond the author's already supplied short action_history and present candidates? E1's released ranking is weaker than an entire agent supplied with these inputs.

## Freeze
Use all five E1 test splits. Scan only current action_history outside quoted strings and read prior actions in the released order. Keep last click, text_input, submit, change or load. Reset to no pointer on load and on any addressable action other than click. For last click, take exact uid and require it is present among current candidates and current editable tag is true. If eligible, override first released candidate. Otherwise select first candidate. Also score UID-only same gate without editable tag as a weaker diagnostic. This is reconstructed for each example with no mutable state across examples.

The outer scanner respects quoted strings and backslash escapes. On malformed unmatched parentheses it stops, retaining parsed complete actions. No correction using test labels. Predict before referring to current gold action. Reuse pinned WebLINX source and labels only as scorer. Compare all identified targets, splitting by five official tests, with 2,000 demo-cluster bootstrap replicates seeded 17112026. Also report count of different selections versus E1's best simple last_click_editable and identical-error coverage. Traces store UIDs and counts only.

## Disconfirmation
If a current-context rule matches or beats E1, E1 offers no evidence that a persistent memory state is needed. If E1 is higher, require paired uncertainty and locate actual history truncation/old-tag mechanisms before transferring it to LLM policies. Either result still does not estimate closed-loop navigation success or superiority over any trained web-agent.

