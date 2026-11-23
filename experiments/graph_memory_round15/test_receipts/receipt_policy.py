"""Read-only checkpoint evidence policies; visible terminal reports and shell status have different sources."""
import re

ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
TIME = r"\s+in\s+\d+(?:\.\d+)?(?:s| seconds?)(?:\s+\([\d:]+\))?"
COUNTER = re.compile(r"(\d+)\s+(?:(subtests?)\s+)?(passed|failed|errors?|skipped|xfailed|xpassed|deselected|warnings?|reruns?|flaky|items? selected|selected)")
TIMER = re.compile(r"(.*?)"+TIME+r"$")
def terminal(output):
    lines=ANSI.sub("",output or "").strip().splitlines()
    if not lines:return "no_evidence",""
    # A final candidate must occupy the final nonblank line. An appended shell postamble loses provenance.
    line = lines[-1].strip()
    body = line.strip("= ").strip()
    match=TIMER.fullmatch(body)
    if not match:return "no_evidence",line
    if match[1] in ("no tests ran","no tests collected","no tests collected (0.00s)"):return "skip_or_empty",line
    parts=[COUNTER.fullmatch(x.strip()) for x in match[1].split(",")]
    if not parts or not all(parts):return "no_evidence",line
    failures=sum(int(x[1]) for x in parts if x[3] in ("failed","error","errors"))
    passes=sum(int(x[1]) for x in parts if not x[2] and x[3]=="passed")
    if failures:return "fail",line
    if passes and any(re.search(r"^!+\s*(KeyboardInterrupt|Interrupted:)|^INTERNALERROR>", s) for s in lines):return "no_evidence",line
    if passes:return "pass",line
    if any(x[3] in ("skipped","deselected","xfailed","xpassed") for x in parts):return "skip_or_empty",line
    return "no_evidence",line

def policies(rc, status, direct, pipefail):
    exit_tag="pass" if rc==0 else "fail" if rc is not None else "abstain"
    summary=status if status in ("pass","fail") else "abstain"
    against_rc=summary if summary!="pass" or rc==0 else "abstain"
    strict=against_rc if against_rc!="pass" or direct or pipefail else "abstain"
    return dict(exit_only=exit_tag,summary=summary,summary_rc=against_rc,strict=strict)
