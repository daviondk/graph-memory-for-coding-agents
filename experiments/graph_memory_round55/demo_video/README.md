# Demonstration walkthrough

[Watch the English MP4](walkthrough.mp4) · [Download the English caption file](captions.srt) · [Four-page proposal](../../graph_memory_round54/submission/paper.pdf) · [Run the same offline system](../../graph_memory_round54/submission/candidate.zip)

The recording shows how an agent chooses its next source, how a visitor can withdraw the evidence for that choice, and how a database can keep an exact ranking across a code change. It runs **3 min 13.16 s** and occupies **5,661,457 bytes**. The English narration uses Microsoft Zira Desktop. Captions are visible in the image. The supplied SRT contains the same timed text.

| Start | Visitor action | Observable outcome |
| --- | --- | --- |
| 00:09 | Compare a literal title with a hyperlink in an archived 2Wiki question. Suppress the selected link and audit again. | Coverage rises from one of the two reference pages to both, then falls back to one. The audit runs after each selection. |
| 00:52 | Allocate one extra file read in an archived pytest session and switch the fourth ranking from embeddings to suggestions. | The deprecations document misses the required file. The acceptance tests cover it. Each read has a chunk receipt. The full 283-session panel gave 20 hits for the suggestion-first rule and 26 for the released 4B embeddings. |
| 01:39 | Advance from revision 16 to 17 in a recorded tool trace and rewind the read version. | An outgoing edge loses one unit of weight. Producer 14 loses its lead to producer 3. The two SQLite history plans agree before, after and on rewind. |
| 02:19 | Step across tox commit `62bd8cf9` and change the cache from eight slots to twelve. | At eight slots the stored bound preserves the eighth-ranked file after its score falls from 30 to 29. The variable-prefix baseline fetches one indexed row. At twelve slots both fetch zero. This was the only differing transition in the six-repository panel of 714 transitions. |

The Wikipedia, pytest and tool-trace consoles execute the packaged SQLite queries on loopback. The tox view re-ranks the frozen scores in the browser and displays the indexed reads from a recorded SQLite run. All four cases use the interactive controls in the pinned release. The cursor halo, close-ups and caption strip were added for the video. Each scene was captured by driving the browser and holding the resulting view for its narration. An offline read after an archived session is a replay. The aggregate metrics for the full panel accompany the selected example. [Pinned source release](https://github.com/daviondk/graph-memory-for-coding-agents/tree/9d2a7a280ee0a084f382762a52547b4b47d0ce56/experiments/graph_memory_round54/submission)

The ICDE demonstration call encourages a supplementary video of up to five minutes and up to 50 MB, in MP4, MPEG or AVI. It describes adding the video after completing the proposal submission. Use the MP4 in **this directory** as the current video supplement. The historical R54 ZIP linked above contains its earlier video. [Official ICDE demonstration call](https://icde2027.github.io/cf-demonstrations.html)

## Rebuild

Use Windows, an installed US English System.Speech voice, the Segoe UI fonts, FFmpeg and FFprobe, and Python with Playwright, Pillow and NumPy. In the recorded environment the versions were Python 3.14, Playwright 1.59.0, Pillow 12.2.0 and NumPy 2.4.4. The exact Chromium and FFmpeg versions appear in [verification.json](verification.json). Chromium can be installed for this interpreter with `python -m playwright install chromium`. Rendering uses a scratch directory outside the repository. From this directory run

```powershell
python -X utf8 -B record.py D:/CodexResearch/x20-r55-film-rebuild --output D:/CodexResearch/x20-r55-film-release
```

The builder verifies the SHA-256 of the input ZIP, starts the local launcher, applies the actions, checks the returned state and captures the actual UI. It synthesizes the narration, aligns each caption to the speech, and builds a standard H.264 / AAC MP4 at 25 fps, 1280 × 816. Software and font versions can affect pixels and compressed bytes. The reference MP4 SHA-256 is `ea9157d84bd3fd30c87552f8cddd61edb7e6ac20e54d8a33b5d2f6b032972a1c`. The scenario, camera and encoding code lives in [scenes.json](scenes.json), [capture.py](capture.py), [record.py](record.py) and [speak.ps1](speak.ps1).

## Verification

The release decodes from start to finish. For each of the 20 scenes the verifier compares a decoded frame with its captioned source image and the decoded audio with the original English speech waveform. All 20 checks passed. The maximum mean absolute RGB error was 2.622 on the 0–255 scale, and each scene's PCM correlation exceeded 0.9999. The browser made zero external requests during interaction. The recorded state receipts include both withdrawal query plans, selected titles, per-file chunk hashes and both tox cache settings. [Scene-by-scene verification](verification.json)

A secondary audio check decodes the delivered AAC stream with the general US English acoustic and language models shipped in PocketSphinx. It receives the audio and scene boundaries. The text captions and proper names are withheld from the recognition engine. All 20 scenes yielded a transcript. Of the 376 distinct reference words counted within scenes, 311 matched a recognized word in the same scene. The recognizer sometimes mistranscribed technical words and the French name. This overlap is a diagnostic of speech content. To rerun this optional check install `pocketsphinx==5.1.1`, make its native runtime libraries available, and execute `python -X utf8 -B check_speech.py`. [Recognition transcripts](speech-check.json)
