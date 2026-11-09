# MuPRO HDF5 reader /1

This additive profile defines `mupro.hdf5@1` and `stk.source.mupro_hdf5@1`.
Existing DAT readers and MuFerro task verification retain their contracts. The public MuFerro
connector 0.2.0 additionally discovers native fields in the selected case's `run.h5`.
Reading an HDF5 field does not establish solver success or scientific validity.

`run.h5` is a reserved optional output name. Submission and compute-side preflight refuse
a case directory that already contains it, before upload or solver execution, so an earlier
run's container cannot be collected as a new result. It remains optional: DAT completion
verification and its required artifacts are unchanged. Other HDF5 input names are not
reserved by this rule.

## Native field

The caller explicitly supplies `/tNNNNNNNN/<field>`: eight ASCII decimal digits and a field name
starting with an ASCII letter, followed by at most 63 ASCII letters, digits or underscores.
The selector must match in full; there is no implicit latest frame or field fallback.
Both selected members must be hard links, respectively to a group and a numeric dataset.

Shape is `(nx, ny, nz, nc)`, all positive. The returned `ImageData` has a C-contiguous
`(nz, ny, nx, nc)` point field. Supported types are float32/64 and signed/unsigned integers of
8/16/32/64 bits; enums, compounds, strings and boolean arrays are refused. Byte order becomes native;
values, including nonfinite floating values, and numeric precision are retained. Native float32 is
not a reader-induced lossy conversion.

Step comes from the selector; physical time is unknown. Origin is zero, spacing one, frame `grid`,
length unit `grid_index`, field unit `unspecified`. Known MuFerro stems use the published quantity
and component meaning only when the component count agrees. Other multicomponent fields, including
six-component fields, remain `array`; no physical units or tensor order are inferred.

`read_hdf5_image(path, selector, *, region=None, stride=None, max_bytes=256*1024*1024)` is the
local reader. Inclusive region bounds are clipped, `None` means an open endpoint, and three positive
stride values select an HDF5 hyperslab. Geometry moves to the first kept point and spacing scales
with stride. Empty selections are errors.

The allocation estimate includes two selected arrays and one complete chunk, doubled for filtered
chunks. It is checked before reading values. HDF5 metadata and its internal cache are outside this
estimate, which is not an RSS guarantee. VDS, external raw storage and soft/external links are
refused. Only built-in filters and h5py's bundled LZF are accepted. No allocated storage, or missing
chunks in a chunked field, is rejected. Allocated fill values and partially written contiguous data
cannot be reliably distinguished from intentional data; this reader is not a completion verifier.

For the local `read_hdf5_image` API, the last path component must be an ordinary file,
without symlink/reparse indirection; callers
provide trusted parents. Reads use a pinned descriptor, with before/after file identity and metadata
checks. POSIX uses same-API status-change time; Windows queries the handle's `FILE_BASIC_INFO.ChangeTime`.
An unavailable change-time query is an error. These checks detect changes during the read, without
promising an operating-system snapshot or locking an external producer.

## FileSource and graph

`suan.connectors.mupro.source.fingerprint(source, path, selector)` hashes actual stream bytes, with
no metadata hash shortcut. `source.read(..., expected_sha256=...)` streams the exact input into a
private temporary file, verifies the planned SHA, then invokes the same selected-field reader on
that open stream. POSIX unlinks the temporary file at creation; Windows uses delete-on-close.
Closing handles also releases the copy when the worker is killed. Both operations cap the source at 1 GiB and check
cancellation between chunks. A remote FileSource needs no local path. Returned provenance identifies
the original relative path/SHA; a single frame's `SourceRef` binds that path, reader, size, SHA and
native selector, rather than the temporary filename.
FileSource path rules apply before copying: `LocalFiles` allows links whose resolved target stays
inside its binding root; the pinned-reader rule above applies to the verified anonymous copy.
Runtime bindings expose published artifacts only after the task reaches a terminal state; this
profile does not add live access to an actively written Runtime `run.h5`.
The copy uses the host's default temporary filesystem; on tmpfs its bytes consume memory outside
the selected-array estimate and the evaluator's process-RSS accounting. The separate 1 GiB source
cap still applies. Fingerprinting reads the complete source even on cache hits; cache misses read
it once more to create the verified copy. Chunk decoding itself has no cooperative cancel hook;
the graph worker may be terminated to interrupt it.

The graph node requires `binding` and `selector`; `path` defaults to `run.h5`. Optional `extent` is
`[i0,i1,j0,j1,k0,k1]` with nullable, nonnegative inclusive endpoints; `stride` defaults to `[1,1,1]`.
The selected allocation limit is 256 MiB, further restricted by the evaluation's memory budget.
The content fingerprint, selector, extent and stride participate in the data key. Execution verifies
the fingerprint used to plan that key, preventing changed source bytes from populating the old entry.

```json
{"schema":"stk.graph/1","catalog":{"stk":1},"nodes":[
  {"id":"polar","type":"stk.source.mupro_hdf5@1","params":{
    "binding":"data","path":"run.h5","selector":"/t00001000/Polar"}}
],"outputs":{"field":"polar.out"}}
```

The node is available through the shared graph service/CLI and saved project analyses with an
explicit input binding. It does not execute MuPRO or expand agent permissions.

## Run discovery and collection

`MuFerroConnector.describe` inspects `run.h5` in the selected case directory when present. This is
native-format discovery within an identified MuFerro run, not a generic `.h5` filename sniffer.
It verifies one private copy and inspects only two levels of metadata, with a total limit of 4096
visited entries including ignored names. Recognized step groups and fields must satisfy the same
hard-link, shape, numeric type, storage and filter checks as the reader. No field values are read.
Unrecognized names are ignored; malformed recognized objects reject the HDF5 listing. Cancellation is
checked during traversal. Discovery is subject to the same separate 1 GiB container limit.

Dataset IDs are `hdf5:<field>`, so DAT `Polar` and HDF5 `hdf5:Polar` coexist without replacing one
another. Frames retain the exact native selector and observed container SHA/size; field descriptors
retain native dtype and unknown units. One field's shape and dtype must agree across its steps.
`connector.open(..., "hdf5:Polar", result=result)` selects frames with the existing frame-selector
policy, then refuses any source bytes that differ from that observation. A fresh `describe` is
required after an external rewrite. Crop/stride use the same hyperslab reader and preserve dtype.

If this optional container has a profile, dependency or budget error, the connector exposes
`extensions.mupro.hdf5_error` with its stable code/message and publishes no datasets from that
container. Existing DAT fields and energy/progress tables remain readable. Requesting a missing
`hdf5:<field>` handle surfaces the recorded HDF5 diagnostic. Declared over-limit containers need
not be copied just to report the size error. Hard-link aliases remain separate declared selectors;
their names do not establish independent observations or physical time.
`complete` and `verification` retain the existing DAT-run meaning; HDF5 consumers must also check
the separate diagnostic before using this container.

The graph run index exposes these descriptors in `result.datasets`. Its `frames` table and
`muferro_frame@1` remain DAT interfaces; use `mupro_hdf5@1` with a discovered selector for HDF5
analysis. Run-index implementation version 3 binds discovery to its planned container SHA and
rejects additions, removals, rewrites or inability to verify a previously hashed container during
execution. These content-binding failures are errors, not optional-format diagnostics. Replacement connectors
keep their existing `describe` call signature and own native-format policy; the public HDF5 extension
is passed only to the shared public implementation.

The existing MuFerro project collector includes `case/run.h5` when published by the same successful
task. It checks artifact size/SHA, validates native field metadata, requires at least one discovered
field and rejects any grid that differs from the frozen case. It registers the original
file with that run's result row; repeated collection does not submit work. Downstream workflow
snapshots retain the whole container and still obey the existing 100-file/256 MiB input budget.

HDF5 discovery does not replace the DAT-based completion verifier: an HDF5-only directory can be
read without establishing a successful MuPRO run. Real licensed output and scientific validity
require separate evidence; the automatic collector currently still requires the existing verified
DAT outputs as well as any HDF5 sidecar.
