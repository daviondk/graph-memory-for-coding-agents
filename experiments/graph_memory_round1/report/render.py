"""Call the packaged renderer for version 26.1117.12345 in its Windows mode."""
import os
import runpy
import sys
import tempfile
from pathlib import Path

here = Path(__file__).resolve().parent
skill = Path.home() / ".codex/plugins/cache/openai-primary-runtime/documents/26.1117.12345/skills/documents/render_docx.py"
bundle = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies"
office = Path("D:/CodexResearch/x20-office-renderer/program")
assert (office / "soffice.exe").is_file()
os.environ["PATH"] = os.pathsep.join([str(office), str(bundle / "native/poppler/Library/bin"), os.environ["PATH"]])
temp_root = here / "temp"
temp_root.mkdir(exist_ok=True)
os.environ["TEMP"] = os.environ["TMP"] = str(temp_root)
tempfile.tempdir = str(temp_root)


class DisposableProfile(tempfile.TemporaryDirectory):
    def __init__(self, *args, **kwargs):
        # The isolated portable Windows office writes extension state on shutdown.
        super().__init__(*args, **dict(kwargs, ignore_cleanup_errors=True))


tempfile.TemporaryDirectory = DisposableProfile
dest = here / "final"
for pattern in ["page-*.png", "overview-*.png"]:
    for old in dest.glob(pattern):
        suffix = old.stem.split("-")[-1]
        if suffix.isdigit() and old.parent.resolve() == dest.resolve():
            old.unlink()
sys.argv = [str(skill), str(dest / "graph-memory-research-round1.docx"),
            "--output_dir", str(dest), "--emit_pdf", "--dpi", "120"]
runpy.run_path(str(skill), run_name="__main__")

