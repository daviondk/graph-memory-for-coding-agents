from __future__ import annotations

HARD_CONSTRAINT = (
    "Hard constraint: Do not answer based on your knowledge. Instead, use tool "
    "results as support."
)

_BASE = """You are a QA agent answering questions using only the tools below.

Rules:
- Do NOT answer from your own knowledge. Only use grep, glob, and read_file results as evidence.
- Explore with glob/grep first, read the most relevant files, then call answer exactly once.
- All paths are relative to workspace root (.).
{explore_rule}
{hard_constraint}
{policy_rule}
{workspace_block}
Tool usage:
- Parameter details are defined in each tool schema.
- grep: search file contents; optional path scopes the search root; optional glob filters filenames.
- glob: find paths by filename pattern; optional path scopes the search root.
- read_file: read a file; start_line and end_line must be provided together when using a line range.
- diff: inspect current workspace modifications when available.
- answer: submit the final answer once you have enough evidence.
"""


def build_system_prompt(*, workspace_context: str, policy: str = "raw") -> str:
    workspace = workspace_context.strip()
    if workspace:
        explore_rule = "- Use glob/grep to explore beyond the workspace listing when needed."
        workspace_block = f"\nWorkspace (paths relative to .):\n{workspace}\n"
    else:
        explore_rule = "- Use glob/grep to discover and explore relevant files."
        workspace_block = ""
    if policy == "git":
        policy_rule = "- Before calling answer, call diff exactly once after your final evidence-gathering step."
    else:
        policy_rule = ""
    return _BASE.format(
        explore_rule=explore_rule,
        hard_constraint=HARD_CONSTRAINT,
        policy_rule=policy_rule,
        workspace_block=workspace_block,
    )
