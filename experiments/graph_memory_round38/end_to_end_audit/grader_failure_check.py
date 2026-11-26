"""Ensure an invalid hunk is classified as unobserved rather than as a resolved/legitimate failure."""
import json, tempfile
from pathlib import Path
from grade_patch import grade
from inputs import D,R,save
def main():
    invalid=b"diff --git a/traitlets/__init__.py b/traitlets/__init__.py\n--- a/traitlets/__init__.py\n+++ b/traitlets/__init__.py\n@@ -1 +1 @@\n-nonexistent fixed hunk 9c1e94156a\n+fixture\n"
    with tempfile.TemporaryDirectory(dir=R) as t:
        p=Path(t)/"invalid.diff";p.write_bytes(invalid)
        result=Path(t)/"out.json";code=grade(p,result);data=json.loads(result.read_text(encoding="utf8"))
        assert code==2 and not data["complete_observation"] and not data["parsed_statuses"]
        save(D/"failure-check.json",dict(graded_as_unobserved=True,harness_exit=code,container_exit=data["exit_code"],parsed_tests=0,
             patch_sha256=data["patch_sha256"],log=result.with_suffix(".log").read_text(encoding="utf8")))
if __name__=="__main__":main()
