# Public native document fixtures

## Frozen video

`frozen-preview.mp4` is a public synthetic six-second MP4: three seconds of red followed
by three seconds of blue at 320×180/10 fps, with a generated 440 Hz tone. It contains
H.264 Baseline level 3.0, yuv420p video and AAC audio; no source recording or private data.
SHA-256: `a54fb5baf8ca34545a8e31ea46c8801347db722cc9c876279186ab8c94f860d1` (41,558 bytes).
FFprobe independently reported both streams and six-second duration. CPU bridge tests use
the exact bytes to check frozen-source and player bindings; this does not prove browser playback.
FFmpeg is a fixture-generation tool, not a new product dependency.

Generation command:

```bash
ffmpeg -nostdin -hide_banner -loglevel error -n \
  -f lavfi -i 'color=c=red:s=320x180:r=10:d=3' \
  -f lavfi -i 'color=c=blue:s=320x180:r=10:d=3' \
  -f lavfi -i 'sine=frequency=440:sample_rate=48000:duration=6' \
  -filter_complex '[0:v][1:v]concat=n=2:v=1:a=0[video]' -map '[video]' -map 2:a \
  -c:v libx264 -profile:v baseline -level:v 3.0 -pix_fmt yuv420p -threads 1 \
  -c:a aac -b:a 48k -movflags +faststart -fflags +bitexact \
  -flags:v +bitexact -flags:a +bitexact -metadata creation_time=2000-01-01T00:00:00Z \
  frozen-preview.mp4
```

## Native PDF boundary regression

`macos-pdf-scaled-boundaries.png` is an unchanged public synthetic OS capture from
[Desktop run 40472799346](https://github.com/sijintech/stk/actions/runs/40472799346),
commit `3ac896235ca819c12a0d73304c5cd59436fe5ffb`, macOS PDF cycle 1, `visible-page1`.
SHA-256: `1a42957cd8293f70827485b6c00bc48bd12b13eafd3cc2856bb2843aab10c795`.

The 1024×653 client contains the native viewport `[631, 200, 385, 256]` in top-left
coordinates. PDF page 1 is visible, with 1–2 pixel mixtures at adjacent stripe
boundaries. The original contiguous-color predicate rejected those pixels.
The CPU replay checks page 1 inside this viewport, rejects page 2, and rejects both
markers outside it. Independent generated positive and negative cases exercise
other scales, both page orders and invalid transitions. Replay does not replace
new native lifecycle and OS capture acceptance on macOS or Windows.
