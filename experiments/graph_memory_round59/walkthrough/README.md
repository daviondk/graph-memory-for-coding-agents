# Reopening graph memory — English walkthrough

[Play the 1 min 55.4 s video](walkthrough.mp4) · [English captions](captions.srt) · [Open the interactive demo](../demo/index.html)

The video starts with the cost of reopening an exact SQLite graph index, then follows the second recorded Sphinx request from its C++ domain module through ten source commits and eight ranked files. It shows why address lists pay off at 4 KiB on the transfer workload and why event bodies alone win at 1 KiB. The final scenes demonstrate recovery of one missing event ID, the ambiguity with two missing IDs, and the budget reversal on six held-out repositories.

Nine scenes were captured from live controls in a local Microsoft Edge session with network access disabled. Each scene holds its verified browser state while an English system voice explains the result. The captions are available both on screen and as a separate SRT. The 2,894,638-byte MP4 contains 2,885 video frames at 25 fps, 1280 × 816 H.264 video, and a mono AAC track. The verification repeats the 23 interface actions, checks the displayed values, decodes the entire file, and compares a stable frame and its audio with fresh capture and speech for each scene. [Verification](verification.json) · [Narration](scenes.json)

With the checkout on Windows and the earlier recorder dependencies available (Playwright, Edge, FFmpeg, Pillow, NumPy and Microsoft Zira Desktop), run:

```console
python -B record_demo.py --verify
```

Run `python -B record_demo.py` to rebuild the recording and captions. [Recorder](record_demo.py)
