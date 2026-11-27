# When the last copy leaves

[Play the English walkthrough (1 min 50 s)](walkthrough.mp4) · [Download English captions](captions.srt) · [Open the offline interactive demo](../demo/index.html)

The example follows a query for files that changed alongside `reader.py`. When events 13 and 45 lose their last resident copy, recording their addresses lets the reader recover the full history and fetch only two missing bodies. Turning notifications off reproduces the same ranking after one extra posting request. The example has eight constructed events. The repository trials use actual Git histories from six projects. The final views show the payload tie at 4 KiB, the faster append-efficient full list on the local CPU comparison, and the equal payload totals on short observed editor windows at 1 KiB. [Repository trials](../coverage/REPORT_RU.md)

Nine narrated scenes use screenshots of eleven live interactions in Microsoft Edge with network access disabled. The MP4 contains 2,742 H.264 frames at 25 fps, 1280 × 816 pixels, English on-screen captions and mono AAC speech. It is 2,840,144 bytes long. Offline verification repeats the browser interactions, compares the exact ranks, decodes all frames, and compares a fresh screenshot and speech with the decoded image and audio from each scene. [Measurements and input hashes](verification.json) · [Narration](scenes.json)

On Windows with Edge, Playwright, FFmpeg, Pillow, NumPy and Microsoft Zira Desktop available, run the following command inside this directory.

```console
python -B record_demo.py --verify
```

Use `python -B record_demo.py` to rebuild the movie, captions and verification manifest. [Recorder](record_demo.py)
