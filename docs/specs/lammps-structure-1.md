# LAMMPS molecular structure reader, version 1

This additive E1d contract uses the existing `stk.graph/1`, `stk.data/1` PolyData and
`stk.payload/2` points/lines primitives. It does not implement the reserved `particles`
dataset kind or change any existing node declaration. The catalog additions are
`stk.source.lammps_structure@1`, `stk.render.molecule_atoms@1` and
`stk.render.molecule_lines@1`; the shipped preset is `lammps-molecule`.

## Input and limits

The caller explicitly declares `atom_style full` and `units real`. A LAMMPS data file
does not encode the unit system or boundary conditions; the reader does not infer them.
The required static file supplies atom IDs, molecule IDs, atom types, charges,
coordinates, masses and explicit bonds. Numeric coefficient sections, velocities,
angles, dihedrals and impropers are validated and retained as applicable. The reader
does not infer bonds from distances, chemical elements from masses, charges from
types, or missing measurements from zero. Atom type legend names use the first token
of a supplied Masses comment, otherwise a numeric type label.

An optional UTF-8 text dump supplies complete frames with `id` and `type` columns and
one complete coordinate triplet. `mol` and `q` are optional: molecule identity and
charge then come from the static topology. Every frame must contain exactly the same
atom IDs/types/molecules as the topology. Changed charges are accepted only as finite
explicit dump values. IDs need not be contiguous or ordered; returned rows are sorted
by actual atom ID, and bonds refer to those IDs rather than row indices.

The supported cells are orthogonal and restricted triclinic. Dump outer bounds are
converted to the true cell origin and vectors, including the `xy`, `xz`, `yz` tilts;
dump boundary flags determine periodic directions. General triclinic `abc origin`,
binary/compressed dumps, changing atom identity, empty or incomplete trajectories,
duplicate/backward timesteps and unsupported sections fail explicitly. Reset the
timestep before enabling a dump. A malformed later frame rejects the trajectory even
when an earlier frame was requested.

The reader hard limits are 256 MiB per input file, 50,000 atoms, 100,000 bonds,
500,000 bonded terms or coefficient records, 10,000 frames, 8,192 bytes per line,
32-bit positive atom/type IDs and nonnegative timesteps through 2,147,483,647.
Periodic bond display allows at most 128 pieces per bond and 200,000 segments in total;
an exact closest-image search permits at most 10,000 lattice candidates. Inputs or
ill-conditioned cells that exceed these limits fail rather than allocate an unbounded
result. Cancellation is checked while hashing, parsing, indexing and creating bonds.

## Coordinates and periodic display

Coordinate precedence is `xu/yu/zu`, `xsu/ysu/zsu`, `x/y/z`, then `xs/ys/zs`. Scaled
coordinates use the actual cell matrix. Wrapped coordinates with complete `ix/iy/iz`
are unwrapped exactly once; an already unwrapped triplet is not translated again.
Wrapped coordinates without images remain labelled `wrapped`. They are unsuitable
for an unwrapped diffusion analysis; no crossing history is invented.

`wrapped_display=true` wraps points only in directions explicitly marked periodic by
the dump and splits explicit bonds at cell boundaries. With unwrapped coordinates,
the source displacement is retained. For wrapped-only input, the shortest lattice
image is a declared display convention; triclinic nearest images use an exact bounded
search, not componentwise fractional rounding. Static data has unknown boundary flags
and is not automatically wrapped. `wrapped_display=false` retains source point
coordinates; wrapped-only bonds still use the documented shortest-image convention.

## Graph and preset interface

`stk.source.lammps_structure@1` takes a FileSource `binding`, relative `topology`
(default `state.data`), relative `trajectory` (default empty/static), `step`
(`latest`, `first` or an exact available integer), and `wrapped_display` (default true).
Paths must remain inside the binding. Complete trajectory steps are reported through
the existing graph parameter choices, supporting the current Viewer timeline. Static
data has no fabricated timestep. The source scans frames with bounded memory and
caches at most four validated offset indexes; it never stores all frame coordinates.
Content hashes, the selected step and the reader version enter the graph cache key.
Changing appearance parameters reuses molecular geometry; changed source bytes or a
new timestep invalidate it.

Before reusing a trajectory index, both frame reads and graph fingerprints verify the
complete original byte SHA-256 on every platform. A changed file signature rejects an
old index immediately; an unchanged signature is insufficient evidence of unchanged
bytes. The graph discards a stale index and validates the current complete trajectory
again. Hashing is cancellable and restores an existing stream's position, including on
failure. Each verification reads up to the 256 MiB file limit; cached offset lookup
therefore still incurs a full bounded file read. The internal fingerprint verifier
revision also invalidates graph entries produced before this verification rule.

The source outputs are `atoms` (PolyData points), `bonds` (PolyData two-point segments),
`box` (PolyData containing the actual twelve cell edges), and JSON `diagnostics`.
Coordinates and floating source attributes remain float64 before payload encoding,
with length unit `angstrom`. Payload/GPU display attributes may be encoded as float32;
they are not an exact float64 position or charge query. Atom fields are `atom_id`,
`molecule_id`, categorical `atom_type`,
`charge` (in elementary charges), and `source_position` (the original coordinates
after a documented image/scaled conversion). Bond cell fields are `bond_id`,
`bond_type`, `atom_a` and `atom_b`; periodic pieces retain their original bond identity.
Provenance records both original files' raw byte SHA-256 digests.

The preset parameters are `topology`, `trajectory`, `step`, `wrapped_display`,
`radius` and `view`. It emits `view` and `diagnostics`. Render layer IDs are `atoms`,
`bonds`, `box`, `legend` and `axes`. Atoms use payload points with
`appearance.render_as="spheres"`; `radius` is a visual radius in angstrom, not a
physical atomic or van der Waals radius. Bonds and cell edges use genuine indexed
line segments. Type colours and names refer to force-field types rather than guessed
elements. The default local viewer input is the verified collected case directory;
the LAMMPS facade controls which collected topology/dump names may be opened.

## Position queries and acceptance scope

Molecular layers declare neither a volume grid nor `pick.probe`. The current volume
field probe refuses molecular sources; a picked pixel is not converted to an assumed
atom ID. `suan.lammps.structure.atom_sample(frame, atom_id)` returns exact original
float64 position, charge, type and molecule by an explicitly supplied real atom ID,
and rejects absent IDs. Interactive atom picking is a later UI capability.

Parser and graph acceptance covers unsorted IDs, noncontiguous IDs, explicit topology
and original values, all six coordinate/image forms, restricted triclinic bounds,
periodic splitting, independent nearest-image checks, damaged complete-frame inputs,
resource rejection, cancellation, content invalidation, timeline choices, payload
spheres/lines/attributes and the actual scripting field-probe refusal. Native GPU
drawing, PET protocol scientific validity, adequate trajectory duration and material
property conclusions require their separate acceptance records; this contract alone
does not establish them.
