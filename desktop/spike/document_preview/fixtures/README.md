# Native PDF boundary regression fixture

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
