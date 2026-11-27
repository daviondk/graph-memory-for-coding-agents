# English demonstration video

[Play the current walkthrough](walkthrough.mp4) · [Subtitles](captions.srt) · [Four-page paper](../manuscript/paper.pdf) · [Offline two-file view](../seed_pair/demo.html)

The 1 min 57.44 s recording shows the single-file NetworkX replay, two actual SQL queries about Dask and Xarray changes, and two states of the identical-pair-count construction. The Dask and Xarray controls share exactly the same past events. Viewers can hide the labels, inspect the source revisions and compare the pair overlap control. In the last scene the selected history changes which C file belongs with the two known files while preserving every pair count.

The file contains H.264 video and English AAC audio, burned-in captions and nine captured states with actual browser actions. Size is 2,858,772 bytes. The English narration uses an installed Windows speech voice. The verifier decoded the entire MP4, checked video structure and compared the decoded image and sound of each scene against its recorded browser state and input voice waveform. [Verification and SHA-256](verification.json)

To reproduce on Windows from this folder, run `python -X utf8 -B record_current.py` with Chromium for Playwright, FFmpeg, Pillow, NumPy, an English Windows voice and the preceding repository artifacts available. It reads the bundled replay database over loopback and the previous single-file offline view. The rendered images and intermediate PCM audio live in a temporary directory. The ICDE demonstration call allows at most five minutes for the optional video. [Official call](https://icde2027.github.io/cf-demonstrations.html)
