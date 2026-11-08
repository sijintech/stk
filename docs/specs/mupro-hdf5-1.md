# MuPRO HDF5 reader /1

This additive profile defines `mupro.hdf5@1` and `stk.source.mupro_hdf5@1`.
Existing DAT readers, MuFerro task verification and automatic run discovery retain their contracts.
Reading an HDF5 field does not establish solver success or scientific validity.

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

The last path component must be an ordinary file, without symlink/reparse indirection; callers
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
explicit input binding. It does not add automatic HDF5 result discovery, change the DAT-based
MuFerro completion verifier, execute MuPRO, or expand agent permissions. Those are separate increments.
