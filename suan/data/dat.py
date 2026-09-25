"""Fast reader and writer for regular-grid field DAT files (MuPRO / muFerro, reader ``mupro.dat@1``).

A field DAT is text::

    nx ny nz [n4 [n5]] [! comment]      header: 3-5 positive integers, optional Fortran comment
    i j k v1 ... vn                      3 index columns: one row per point, n >= 1 values
    i j k c v  /  i j k a b v            4/5 index columns: one row per (point, component)

Indices are one-based. MuPRO writes Fortran fixed-width rows (``i6`` indices and
``es15.7e3`` values such as ``-1.2345678E+003``, or ``D`` exponents) with x
slowest and the last index fastest. For 4/5 index columns the components are
the trailing header dimensions in C order (component = a * n5 + b).

:func:`read_dat` takes a vectorized fixed-width path (a ``uint8`` view of each
chunk of rows, exact decimal decoding, an O(n) row-order check) and falls back
to a whitespace-token parser for anything else (free-format rows, comments,
blank lines, other widths). Both give the values ``numpy.loadtxt`` gives,
including 3-digit exponents; the fallback reproduces the historical
``toolkits.sviz.field.read_field`` checks and messages, while the fixed-width
path detects the same errors. Rows may be in any order; a duplicate or missing
grid point is an error. Non-finite values are returned as read (``read_field``
rejects them itself).

:func:`write_dat` writes the same layouts quickly (fixtures, conversions); its
mantissas are rounded in binary floating point, so the last digit can differ
from C ``printf`` in rare halfway cases (the reader parses whatever is written).
"""
from collections import deque
from dataclasses import dataclass
import io
import math
import os
from pathlib import Path
import re

__all__ = [
    "DEFAULT_CHUNK_BYTES", "READER_ID",
    "DatError", "DatHeader",
    "dat_info", "frame_name", "read_dat", "read_dat_image", "read_header", "write_dat",
]

READER_ID = "mupro.dat@1"
DEFAULT_CHUNK_BYTES = 8 * 1024 * 1024
_MAX_LINE = 1 << 20

NOT_GRID = ("Not a regular-grid field DAT: the first line must hold 3–5 integer dimensions "
            "(tables such as energy_out.dat are time series)")
BAD_HEADER = "DAT header must contain 3–5 positive dimensions"
BAD_COUNT = "DAT point count or component count does not match the header"
BAD_INDEX = "DAT indices must be integral, one-based and inside dimensions"
DUPLICATE = "DAT contains duplicate or missing grid points"
BAD_INDEXED = "Indexed component DAT requires one value per index tuple"

_FRAME = re.compile(r"^([A-Za-z][A-Za-z0-9_]{0,7})\.(\d{8})\.dat$")
_FLOAT_TOKEN = re.compile(rb"([+-]?)(\d+)\.(\d*)(?:([EeDd])([+-])(\d{1,4}))?")
_WHITESPACE = b" \t\r\n"


class DatError(ValueError):
    """A malformed field DAT (the messages are those of ``toolkits.sviz.field.read_field``)."""


class _NotFixed(Exception):
    """Internal: the fixed-width path does not apply; use the general parser."""


def _np():
    import numpy
    return numpy


@dataclass(frozen=True)
class DatHeader:
    """The header line: ``dimensions`` (3-5 integers), the Fortran ``comment`` and the line's byte ``size``."""

    dimensions: tuple
    comment: str | None
    size: int

    @property
    def grid(self):
        """Point counts ``(nx, ny, nz)``."""
        return tuple(self.dimensions[:3])

    @property
    def index_columns(self):
        return len(self.dimensions)

    @property
    def component_shape(self):
        """Trailing header dimensions of an indexed-component DAT (``()`` for 3 index columns)."""
        return tuple(self.dimensions[3:])

    @property
    def rows(self):
        """Expected data rows."""
        return math.prod(self.dimensions)


def _parse_header(stream):
    raw = stream.readline(_MAX_LINE)
    cr = raw.find(b"\r")
    if cr != -1 and raw[cr + 1:cr + 2] != b"\n":  # old Mac line breaks, as text-mode readline splits them
        raw = raw[:cr + 1]
    text = raw.decode("utf-8") if raw.endswith((b"\n", b"\r")) or len(raw) < _MAX_LINE \
        else raw.decode("utf-8", "replace")
    try:
        # MuPRO's library writer appends a Fortran comment: 'nx ny nz ! comment: nx ny nz'.
        dimensions = tuple(int(v) for v in text.split("!", 1)[0].split())
    except ValueError:
        raise DatError(NOT_GRID) from None
    if not 3 <= len(dimensions) <= 5 or any(n < 1 for n in dimensions):
        raise DatError(BAD_HEADER)
    comment = text.split("!", 1)[1].strip() if "!" in text else None
    return DatHeader(dimensions, comment, len(raw))


def read_header(path):
    """Parse the header line only (raises :class:`DatError` like :func:`read_dat`)."""
    with open(path, "rb") as stream:
        return _parse_header(stream)


def _token_spans(line):
    spans, start = [], None
    for position, byte in enumerate(line):
        if byte in _WHITESPACE:
            if start is not None:
                spans.append((start, position))
                start = None
        elif start is None:
            start = position
    if start is not None:
        spans.append((start, len(line)))
    return spans


def dat_info(path):
    """Grid and component count from the header and the first data row (field values are not parsed).

    ``path`` is a file path or a binary stream positioned at the start.
    ``{"dimensions": [nx, ny, nz], "components": nc | None, "index_columns": 3-5,
    "header": [...], "comment": str | None}``; ``components`` is ``None`` when a
    3-index file has no readable first row.
    """
    if hasattr(path, "readline"):
        return _info(path)
    with open(path, "rb") as stream:
        return _info(stream)


def _info(stream):
    header = _parse_header(stream)
    if stream.seekable():
        stream.seek(header.size)  # an old-Mac header ends at its CR
    components = math.prod(header.component_shape) if header.index_columns > 3 else None
    if components is None:
        first = stream.readline(_MAX_LINE)
        while first and not first.strip():
            first = stream.readline(_MAX_LINE)
        tokens = first.split()
        components = len(tokens) - 3 if len(tokens) > 3 and not first.lstrip().startswith(b"#") else None
    return {"dimensions": list(header.grid), "components": components, "index_columns": header.index_columns,
            "header": list(header.dimensions), "comment": header.comment}


def frame_name(name):
    """``("Polar", 1000)`` for ``Polar.00001000.dat`` (a muFerro frame), else ``(None, None)``."""
    match = _FRAME.match(Path(name).name)
    return (match[1], int(match[2])) if match else (None, None)


# ---------------------------------------------------------------------------
# Fixed-width path: every row has the same length and every token ends at the same column


_DIGITS = None
_TEN = None


def _digit_lut():
    """0-9 for ASCII digits, 10 for a blank, 11 for anything else."""
    global _DIGITS
    if _DIGITS is None:
        np = _np()
        _DIGITS = np.full(256, 11, dtype=np.uint8)
        _DIGITS[48:58] = np.arange(10, dtype=np.uint8)
        _DIGITS[32] = 10
    return _DIGITS


def _powers():
    """``10.0 ** k`` for k = 0..22, all exact in float64."""
    global _TEN
    if _TEN is None:
        np = _np()
        _TEN = np.array([float(10 ** k) for k in range(23)])  # exact: 5**22 < 2**53
    return _TEN


@dataclass
class _FloatTemplate:
    """Normalized bytes of one fixed-width value field, learnt from the first data row.

    Rows are normalized before comparing: digits become 1, a mantissa sign
    (``+``/``-``) a blank, the exponent letter (E/e/D/d) ``d`` and the exponent
    sign ``+``. Rows that differ (NaN, other widths) use NumPy's parser.
    """

    width: int
    expected: object       # (w rounded up to 8,) uint8
    sign: int | None       # byte that holds the mantissa sign or a blank
    integer: tuple         # [start, stop) of the integer digits
    fraction: tuple        # [start, stop) of the fraction digits
    exp_char: int | None
    exp_sign: int | None
    exponent: tuple        # [start, stop) of the exponent digits
    guarded: bool          # the field starts with a checked blank (so no token spans the boundary)


def _float_template(field):
    """Template of one value field, or ``None`` when the first row is not ``[+-]d+.d*[EeDd][+-]d+``."""
    np = _np()
    token = field.lstrip(_WHITESPACE)
    start = len(field) - len(token)
    match = _FLOAT_TOKEN.fullmatch(token)
    if not match or len(match[2]) + len(match[3]) > 15:
        return None
    sign, integer, fraction, exp_char, _, exp_digits = match.groups()
    width = len(field)
    expected = np.zeros(-(-width // 8) * 8, dtype=np.uint8)
    expected[:width] = np.frombuffer(field, dtype=np.uint8)
    at = start + len(sign)
    sign_at = start if sign else (start - 1 if start > 0 else None)
    integer_span = (at, at + len(integer))
    fraction_span = (integer_span[1] + 1, integer_span[1] + 1 + len(fraction))
    expected[integer_span[0]:integer_span[1]] = 1
    expected[fraction_span[0]:fraction_span[1]] = 1
    if sign_at is not None:
        expected[sign_at] = 32
    exp_at = exp_sign_at = None
    exponent_span = (fraction_span[1], fraction_span[1])
    if exp_char:
        exp_at, exp_sign_at = fraction_span[1], fraction_span[1] + 1
        exponent_span = (exp_at + 2, exp_at + 2 + len(exp_digits))
        expected[exp_at] = 0x64
        expected[exp_sign_at] = 43
        expected[exponent_span[0]:exponent_span[1]] = 1
    return _FloatTemplate(width, expected, sign_at, integer_span, fraction_span, exp_at, exp_sign_at,
                          exponent_span, sign_at is not None and sign_at > 0)


def _numpy_floats(field):
    """NumPy's (correctly rounded) parser for rows the template does not cover; D exponents allowed."""
    np = _np()
    raw = np.array(field, dtype=np.uint8, order="C")
    exponent = (raw == 68) | (raw == 100)
    if exponent.any():
        raw[exponent] = 69
    try:
        return raw.view(f"S{raw.shape[1]}").ravel().astype(np.float64)
    except ValueError:
        raise _NotFixed from None


def _digit_value(work, span, weights):
    """Integer value (exact float64) of the digits in ``work[:, span]``; the digits are normalized to 1."""
    np = _np()
    a, b = span
    digits = work[:, a:b] - np.uint8(48)
    if b - a == 1:
        value = digits[:, 0].astype(np.float64)
    else:
        value = digits.astype(np.float64) @ weights[b - a - 1::-1]
    work[:, a:b] = digits < 10
    return value


def _parse_floats(field, template, out):
    """Decode a ``(m, w)`` uint8 field into ``out`` (float64, m).

    Template rows use Clinger's fast path: an integer mantissa below 2**53
    multiplied or divided by an exact power of ten (|e| <= 22) is correctly
    rounded, so the result equals strtod and ``numpy.loadtxt``. The digit sums
    are integers below 2**53, exact in any summation order.
    """
    np = _np()
    if template is None:
        out[:] = _numpy_floats(field)
        return
    m = len(field)
    ten = _powers()
    work = np.zeros((m, len(template.expected)), dtype=np.uint8)
    work[:, :template.width] = field
    mantissa = _digit_value(work, template.integer, ten)
    fraction = template.fraction[1] - template.fraction[0]
    if fraction:
        mantissa *= ten[fraction]
        mantissa += _digit_value(work, template.fraction, ten)
    if template.exp_char is not None:
        exponent = _digit_value(work, template.exponent, ten)
        work[:, template.exp_char] = (work[:, template.exp_char] | np.uint8(0x20)) & np.uint8(0xFE)
        column = work[:, template.exp_sign]
        negative = column == 45
        np.negative(exponent, out=exponent, where=negative)
        column[negative] = 43
    else:
        exponent = np.zeros(m)
    exponent -= fraction
    negative = None
    if template.sign is not None:
        column = work[:, template.sign]
        negative = column == 45
        column[negative | (column == 43)] = 32
    words = work.view("<u8")
    expected = template.expected.view("<u8")
    ok = words[:, 0] == expected[0]
    for i in range(1, len(expected)):
        ok &= words[:, i] == expected[i]
    magnitude = np.abs(exponent)
    ok &= magnitude <= 22
    scale = ten[np.minimum(magnitude, 22).astype(np.intp)]
    if (exponent <= 0).all():
        np.divide(mantissa, scale, out=out)
    elif (exponent >= 0).all():
        np.multiply(mantissa, scale, out=out)
    else:
        out[:] = np.where(exponent >= 0, mantissa * scale, mantissa / scale)
    if negative is not None and negative.any():
        np.copysign(out, np.where(negative, -1.0, 1.0), out=out)
    if not ok.all():
        bad = ~ok
        out[bad] = _numpy_floats(field[bad])


def _parse_indices(field):
    """Unsigned integers of a right-aligned ``(m, w)`` field (blanks then digits), else ``_NotFixed``."""
    np = _np()
    digits = _digit_lut()[field]
    if (digits == 11).any():
        raise _NotFixed
    blank = digits == 10
    if blank[:, -1].any() or (blank[:, 1:] & ~blank[:, :-1]).any():
        raise _NotFixed
    digits[blank] = 0
    value = np.zeros(len(field), dtype=np.int64)
    for position in range(field.shape[1]):
        value *= 10
        value += digits[:, position]
    return value


def _read_into(stream, target):
    view = memoryview(target)
    got = 0
    while got < len(view):
        count = stream.readinto(view[got:])
        if not count:
            break
        got += count
    return got


def _blank(column):
    return (column == 32) | (column == 9)


class _Rows:
    """Layout of the fixed-width rows, learnt from the first data row."""

    def __init__(self, first, header):
        np = _np()
        if not first.endswith(b"\n"):
            raise _NotFixed
        dims = header.dimensions
        spans = _token_spans(first)
        k = len(dims)
        if (k == 3 and len(spans) < 4) or (k > 3 and len(spans) != k + 1):
            raise _NotFixed
        self.width = len(first)
        self.ends = [end for _, end in spans]
        starts = [0] + self.ends[:-1]
        self.index_fields = [(starts[t], self.ends[t]) for t in range(k)]
        self.value_fields = [(starts[t], self.ends[t]) for t in range(k, len(spans))]
        self.trailing = self.width - 1 - self.ends[-1]
        self.components = len(spans) - 3 if k == 3 else math.prod(dims[3:])
        self.rows_per_point = 1 if k == 3 else self.components
        self.templates = [_float_template(first[s:e]) for s, e in self.value_fields]
        # Value fields whose template does not check the blank before the token.
        self.boundaries = [s for (s, _), template in zip(self.value_fields, self.templates)
                           if template is None or not template.guarded]
        self.strides = [math.prod(dims[t + 1:]) for t in range(k)]
        self.tables = []
        for t, ((s, e), n) in enumerate(zip(self.index_fields, dims)):
            width = e - s
            # An index filling its field would touch the previous token (whitespace parsing merges them).
            if width > 18 or len(str(n)) > width - (1 if t else 0):
                raise _NotFixed
            text = b"".join(str(v).rjust(width).encode() for v in range(1, n + 1))
            self.tables.append(np.frombuffer(text, dtype=np.uint8).reshape(n, width))
        # Bytes of the z (and component) index fields, identical for every (i, j) line.
        rows_per_line = dims[2] * self.rows_per_point
        self.split = self.index_fields[2][0]
        self.line_pattern = None
        if rows_per_line * (self.index_fields[-1][1] - self.split) <= 16 * 1024 * 1024:
            row = np.arange(rows_per_line)
            self.line_pattern = np.hstack([self.tables[t][(row // self.strides[t]) % dims[t]]
                                           for t in range(2, k)])

    def check(self, rows):
        """Same line length everywhere, blanks after the last token and where no template checks them."""
        width = self.width
        if not (rows[:, width - 1] == 10).all():
            raise _NotFixed
        tail = rows[:, self.ends[-1]:width - 1]
        if tail.size and not (_blank(tail) | (tail == 13)).all():
            raise _NotFixed
        for column in self.boundaries:
            if not _blank(rows[:, column]).all():
                raise _NotFixed

    def values(self, rows):
        np = _np()
        m = len(rows)
        if len(self.index_fields) == 3:
            values = np.empty((m, self.components), dtype=np.float64)
            for column, ((s, e), template) in enumerate(zip(self.value_fields, self.templates)):
                _parse_floats(rows[:, s:e], template, values[:, column])
            return values
        (s, e), = self.value_fields
        values = np.empty(m, dtype=np.float64)
        _parse_floats(rows[:, s:e], self.templates[0], values)
        return values

    def ordered(self, rows, line0, lines, rows_per_line, dims):
        """True if the chunk's index columns are exactly the canonical sequence (x slowest)."""
        np = _np()
        m = len(rows)
        if self.line_pattern is not None:
            by_line = rows.reshape(lines, rows_per_line, self.width)
            line = np.arange(line0, line0 + lines)
            head = np.hstack([self.tables[0][(line // dims[1]) % dims[0]], self.tables[1][line % dims[1]]])
            return bool((by_line[:, :, :self.split] == head[:, None, :]).all()
                        and (by_line[:, :, self.split:self.index_fields[-1][1]] == self.line_pattern).all())
        for t, ((s, e), table) in enumerate(zip(self.index_fields, self.tables)):
            field = rows[:, s:e]
            stride, count, width = self.strides[t], dims[t], e - s
            period = stride * count
            if rows_per_line % period == 0:  # z index and components repeat within each line
                if not (field.reshape(m // period, count, stride, width) == table[None, :, None, :]).all():
                    return False
            else:  # x and y are constant along each line
                value = (np.arange(line0, line0 + lines) // (stride // rows_per_line)) % count
                if not (field.reshape(lines, rows_per_line, width) == table[value][:, None, :]).all():
                    return False
        return True

    def indices(self, rows):
        """One-based indices ``(m, k)`` of rows in any order (``_NotFixed`` if not plain integers)."""
        np = _np()
        index = np.empty((len(rows), len(self.index_fields)), dtype=np.int64)
        for t, (s, e) in enumerate(self.index_fields):
            if t and not _blank(rows[:, s]).all():
                raise _NotFixed
            index[:, t] = _parse_indices(rows[:, s:e])
        return index


def _put_lines(view, block, line0, line1, ny):
    """Copy ``block`` (lines, nz, nc) of consecutive (i, j) lines into the (x, y, z, c) view."""
    line = line0
    while line < line1:
        i, j = divmod(line, ny)
        stop = min(ny, j + (line1 - line))
        view[i, j:stop] = block[line - line0:line - line0 + stop - j]
        line += stop - j


def _workers(threads, tasks):
    if threads is None:
        threads = min(8, os.cpu_count() or 1)
    return max(1, min(int(threads), tasks))


def _read_fixed(stream, header, layout, dtype, chunk_bytes, check, threads):
    np = _np()
    dims = header.dimensions
    nx, ny, nz = dims[:3]
    stream.seek(header.size)
    first = stream.readline(_MAX_LINE)
    width, n_rows = len(first), header.rows
    spans = _token_spans(first)
    trailing = width - 1 - spans[-1][1] if spans else 0
    # The file size is checked before any index table is built: a tiny file whose header promises
    # 30 000 000 rows must not allocate gigabytes of tables first.
    missing = n_rows * width - (os.fstat(stream.fileno()).st_size - header.size)
    if missing < 0:  # only blank lines or blanks may follow the last row
        if -missing > _MAX_LINE:
            raise _NotFixed
        stream.seek(header.size + n_rows * width)
        if stream.read().strip(_WHITESPACE):
            raise _NotFixed
    elif missing > trailing + 1:  # the last row may lack its trailing blanks and line break
        raise _NotFixed
    rows = _Rows(first, header)
    nc = rows.components
    rows_per_line = nz * rows.rows_per_point
    lines_total = nx * ny
    chunk_lines = max(1, int(chunk_bytes) // (rows_per_line * width))
    out = np.empty((nz, ny, nx, nc) if layout == "zyxc" else (nx, ny, nz, nc), dtype=dtype)
    view = out.transpose(2, 1, 0, 3) if layout == "zyxc" else out

    def read(line0, line1):
        nbytes = (line1 - line0) * rows_per_line * width
        raw = np.empty(nbytes, dtype=np.uint8)
        got = _read_into(stream, raw)
        if got < nbytes:
            if line1 != lines_total or nbytes - got > rows.trailing + 1:
                raise _NotFixed
            raw[got:] = 32
            raw[-1] = 10
        return raw

    def parse(line0, line1, raw):
        chunk = raw.reshape(-1, width)
        rows.check(chunk)
        values = rows.values(chunk)
        if rows.ordered(chunk, line0, line1 - line0, rows_per_line, dims):
            _put_lines(view, values.reshape(line1 - line0, nz, nc), line0, line1, ny)
            return None
        return line0, line1, rows.indices(chunk), values

    stream.seek(header.size)
    spans = [(line0, min(line0 + chunk_lines, lines_total)) for line0 in range(0, lines_total, chunk_lines)]
    workers = _workers(threads, len(spans))
    unordered = []
    if workers == 1:
        for line0, line1 in spans:
            if check is not None:
                check()
            result = parse(line0, line1, read(line0, line1))
            if result is not None:
                unordered.append(result)
    else:
        # NumPy releases the GIL in these loops: chunks are decoded in parallel, reads stay sequential.
        from concurrent.futures import ThreadPoolExecutor
        pending = deque()
        with ThreadPoolExecutor(workers, thread_name_prefix="stk-dat") as pool:
            try:
                for line0, line1 in spans:
                    if check is not None:
                        check()
                    pending.append(pool.submit(parse, line0, line1, read(line0, line1)))
                    while len(pending) >= 2 * workers:
                        result = pending.popleft().result()
                        if result is not None:
                            unordered.append(result)
                while pending:
                    result = pending.popleft().result()
                    if result is not None:
                        unordered.append(result)
            except BaseException:
                for future in pending:
                    future.cancel()
                raise
    if unordered:
        _scatter(view, unordered, dims, rows, rows_per_line, n_rows)
    return out


def _scatter(view, chunks, dims, rows, rows_per_line, n_rows):
    """Place chunks whose rows are not in canonical order; the checks of ``read_field`` in its order."""
    np = _np()
    limit = np.array(dims, dtype=np.int64)
    for _, _, index, _ in chunks:
        if (index < 1).any() or (index > limit).any():
            raise DatError(BAD_INDEX)
    seen = np.ones(n_rows, dtype=bool)  # rows of in-order chunks are exactly their canonical rows
    for line0, line1, _, _ in chunks:
        seen[line0 * rows_per_line:line1 * rows_per_line] = False
    strides = np.array(rows.strides, dtype=np.int64)
    for _, _, index, values in chunks:
        index = index - 1
        linear = index @ strides
        if seen[linear].any() or len(np.unique(linear)) != len(linear):
            raise DatError(DUPLICATE)
        seen[linear] = True
        if index.shape[1] == 3:
            view[index[:, 0], index[:, 1], index[:, 2]] = values
        else:
            view[index[:, 0], index[:, 1], index[:, 2], index[:, 3:] @ strides[3:]] = values


def _read_general(stream, header, layout, dtype):
    """Whitespace tokens (comments and blank lines allowed), with the checks of ``read_field``.

    The text is streamed line by line into ``numpy.loadtxt`` (no whole-file string copies).
    """
    np = _np()
    exponents = {ord("D"): "E", ord("d"): "e"}
    text = io.TextIOWrapper(stream, encoding="utf-8", newline=None)
    try:
        rows = np.loadtxt((line.translate(exponents) for line in text), ndmin=2)
    finally:
        text.detach()  # the caller owns (and closes) the binary stream
    dimensions = header.dimensions
    coordinates = len(dimensions)
    shape = dimensions[:3]
    if rows.shape[0] != math.prod(dimensions) or rows.shape[1] <= coordinates:
        raise DatError(BAD_COUNT)
    coords = rows[:, :coordinates].astype(int) - 1
    if not np.array_equal(coords + 1, rows[:, :coordinates]) or (coords < 0).any() \
            or (coords >= np.array(dimensions)).any():
        raise DatError(BAD_INDEX)
    # One O(n) count instead of np.unique(coords, axis=0): n points inside the grid are distinct iff all counted once.
    if (np.bincount(np.ravel_multi_index(coords.T, dimensions), minlength=len(coords)) != 1).any():
        raise DatError(DUPLICATE)
    if coordinates == 3:
        data = np.empty(shape + (rows.shape[1] - 3,))
        data[coords[:, 0], coords[:, 1], coords[:, 2]] = rows[:, 3:]
    else:
        if rows.shape[1] != coordinates + 1:
            raise DatError(BAD_INDEXED)
        tensor = np.empty(dimensions)
        tensor[tuple(coords[:, i] for i in range(coordinates))] = rows[:, -1]
        data = tensor.reshape(shape + (math.prod(dimensions[3:]),))
    if layout == "zyxc":
        return np.ascontiguousarray(data.transpose(2, 1, 0, 3), dtype=dtype)
    return data.astype(dtype, copy=False)


def read_dat(path, *, layout="zyxc", dtype="float64", chunk_bytes=DEFAULT_CHUNK_BYTES, check=None, threads=None):
    """Read a field DAT into a C-contiguous array.

    ``layout="zyxc"`` gives ``(nz, ny, nx, nc)`` (VTK order, the STK in-memory
    layout); ``"xyzc"`` gives ``(nx, ny, nz, nc)`` (``read_field``'s order).
    ``dtype`` is ``float64`` or ``float32`` (values are decoded in float64 first).
    Text is read in chunks of about ``chunk_bytes``, decoded by up to ``threads``
    worker threads (default ``min(8, cpu_count)``; at most ``2 * threads`` chunks
    are held at once); ``check`` is called between chunks (e.g.
    ``NodeContext.check`` for cancellation). Raises :class:`DatError` (a
    ``ValueError``) for malformed files.
    """
    np = _np()
    if layout not in ("zyxc", "xyzc"):
        raise ValueError("layout must be 'zyxc' or 'xyzc'")
    dtype = np.dtype(dtype)
    if dtype not in (np.float64, np.float32):
        raise ValueError("dtype must be float64 or float32")
    with open(path, "rb") as stream:
        header = _parse_header(stream)
        try:
            return _read_fixed(stream, header, layout, dtype, chunk_bytes, check, threads)
        except _NotFixed:
            stream.seek(header.size)
            return _read_general(stream, header, layout, dtype)


def _identifier(text, pattern, fallback):
    text = re.sub(r"[^A-Za-z0-9_]", "_", text)[:128]
    return text if text and re.match(pattern, text) else fallback


def read_dat_image(path, *, name=None, id=None, dtype="float64", spacing=None, origin=None,
                   length_unit="grid_index", unit="unspecified", quantity=None, tensor=None, component_names=None,
                   step=None, provenance=None, chunk_bytes=DEFAULT_CHUNK_BYTES, check=None, threads=None):
    """Read a field DAT as :class:`suan.data.model.ImageData` with one point field.

    The field is named ``name`` (default: the frame stem of ``<Stem>.<step:08d>.dat``,
    else the file stem); ``step`` defaults to the frame name's step. Geometry
    defaults to origin 0 and spacing 1 in ``grid_index`` units (DAT indices).
    ``float32`` marks the field ``lossy``. Units are never guessed.
    """
    from .model import ImageData, TimeInfo
    path = Path(path)
    stem, frame_step = frame_name(path.name)
    name = name or stem or _identifier(path.name.split(".")[0], r"^[A-Za-z0-9_]", "field")
    step = frame_step if step is None else step
    values = read_dat(path, layout="zyxc", dtype=dtype, chunk_bytes=chunk_bytes, check=check, threads=threads)
    nz, ny, nx, _ = values.shape
    image = ImageData((nx, ny, nz), origin if origin is not None else (0.0, 0.0, 0.0),
                      spacing if spacing is not None else (1.0, 1.0, 1.0), length_unit=length_unit,
                      id=id or _identifier(name, r"^[A-Za-z0-9_]", "image"),
                      time=TimeInfo(step=step) if step is not None else None, provenance=provenance)
    meta = {"unit": unit}
    if quantity is not None:
        meta["quantity"] = quantity
    if component_names is not None:
        meta["component_names"] = tuple(component_names)
    if values.dtype.name == "float32":
        meta["lossy"] = True
    image.add_field(name, values, tensor=tensor, **meta)
    return image


# ---------------------------------------------------------------------------
# Writer


def _format_uint(values, width):
    np = _np()
    top = int(values.max()) if len(values) else 0
    if len(values) and (values.min() < 0 or top >= 10 ** width):
        raise ValueError(f"Index does not fit in {width} characters")
    if top <= 100_000:  # grid indices: one formatted row per value, then a gather
        text = b"".join(str(v).rjust(width).encode() for v in range(top + 1))
        return np.frombuffer(text, dtype=np.uint8).reshape(top + 1, width)[values]
    out = np.full((len(values), width), 32, dtype=np.uint8)
    rest = values.astype(np.int64)
    for position in range(width - 1, -1, -1):
        shown = rest > 0 if position < width - 1 else np.ones(len(rest), dtype=bool)
        out[:, position] = np.where(shown, 48 + rest % 10, 32)
        rest = rest // 10
    return out


def _format_es(values, digits, exponent_digits, exponent_char):
    """``ES`` fields with a leading separator: `` -1.2345678E+003`` (digits=7, exponent_digits=3)."""
    np = _np()
    m = len(values)
    width = digits + exponent_digits + 6
    out = np.full((m, width), 32, dtype=np.uint8)
    finite = np.isfinite(values)
    a = np.where(finite, np.abs(values), 0.0)
    nonzero = a > 0
    exponent = np.zeros(m, dtype=np.int64)
    with np.errstate(divide="ignore"):
        exponent[nonzero] = np.floor(np.log10(a[nonzero])).astype(np.int64)
    special = ~finite | (np.abs(exponent) > 290)
    a[special] = 0.0
    exponent[special] = 0
    nonzero &= ~special
    mantissa = np.rint(a * 10.0 ** (digits - exponent)).astype(np.int64)
    for _ in range(3):  # log10 and rounding (9.99999995 -> 10.0000000) can put the mantissa a decade off
        high = mantissa >= 10 ** (digits + 1)
        low = nonzero & (mantissa < 10 ** digits)
        fix = high | low
        if not fix.any():
            break
        exponent += high.astype(np.int64) - low.astype(np.int64)
        mantissa[fix] = np.rint(a[fix] * 10.0 ** (digits - exponent[fix])).astype(np.int64)
    special |= (mantissa >= 10 ** (digits + 1)) | (nonzero & (mantissa < 10 ** digits))
    exponent[special] = 0
    mantissa[special] = 0
    if (np.abs(exponent) >= 10 ** exponent_digits).any():
        raise ValueError(f"A value's exponent does not fit in {exponent_digits} digits")
    out[:, 1] = np.where(np.signbit(values) & finite, 45, 32)
    rest = mantissa
    for position in range(3 + digits, 3, -1):
        out[:, position] = 48 + rest % 10
        rest = rest // 10
    out[:, 3] = 46
    out[:, 2] = 48 + rest % 10
    out[:, 4 + digits] = ord(exponent_char)
    out[:, 5 + digits] = np.where(exponent < 0, 45, 43)
    rest = np.abs(exponent)
    for position in range(width - 1, width - 1 - exponent_digits, -1):
        out[:, position] = 48 + rest % 10
        rest = rest // 10
    for row in np.flatnonzero(special):
        value = float(values[row])
        if math.isfinite(value):
            mant, exp = f"{value:.{digits}E}".split("E")
            text = f"{mant}{exponent_char}{int(exp):+0{exponent_digits + 1}d}"
        else:
            text = "NaN" if math.isnan(value) else ("Infinity" if value > 0 else "-Infinity")
        if len(text) > width - 1:
            raise ValueError(f"Value {value!r} does not fit the field width")
        out[row] = np.frombuffer(text.rjust(width).encode(), dtype=np.uint8)
    return out


def write_dat(path, data, *, layout="xyzc", component_shape=None, digits=7, exponent_digits=3, exponent_char="E",
              index_width=6, comment=None, pad_header=True, trailing_space=True, newline="\n",
              chunk_rows=1 << 20):
    """Write a field DAT in MuPRO's fixed-width style (x slowest).

    ``data`` is ``(x, y, z[, c])`` (``layout="xyzc"``) or ``(z, y, x[, c])``.
    ``component_shape`` selects the row style: ``()`` = 3 index columns and one
    column per component (PELOOP style); ``(nc,)`` or ``(n4, n5)`` = 4/5 index
    columns and one value per row (muFerro's ``mupro_output_4D``). Default: 3
    index columns for one component, else ``(nc,)``. Values are written as Fortran
    ``ES(digits+exponent_digits+5).(digits)E(exponent_digits)``; ``exponent_char="D"``
    writes D exponents. ``comment`` adds ``! comment`` to the header.
    """
    np = _np()
    data = np.asarray(data)
    if data.ndim == 3:
        data = data[..., None]
    if data.ndim != 4 or data.dtype.kind not in "fiu":
        raise ValueError("Expected a real (x, y, z[, c]) array")
    if layout == "zyxc":
        data = data.transpose(2, 1, 0, 3)
    elif layout != "xyzc":
        raise ValueError("layout must be 'xyzc' or 'zyxc'")
    if exponent_char not in ("E", "D", "e", "d"):
        raise ValueError("exponent_char must be E or D")
    nx, ny, nz, nc = data.shape
    if component_shape is None:
        component_shape = () if nc == 1 else (nc,)
    component_shape = tuple(int(n) for n in component_shape)
    if len(component_shape) > 2 or (component_shape and math.prod(component_shape) != nc):
        raise ValueError(f"component_shape {component_shape} does not match {nc} components")
    dims = (nx, ny, nz, *component_shape)
    indexed = bool(component_shape)
    columns = len(dims)
    field = digits + exponent_digits + 6
    row_width = columns * index_width + (1 if indexed else nc) * field + (1 if trailing_space else 0)
    header = "".join(f"{n:{index_width}d}" for n in dims)
    if comment:
        header += " ! " + comment
    if pad_header:
        header = header.ljust(row_width)
    eol = newline.encode()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    points_per_plane = ny * nz
    rows_per_point = nc if indexed else 1
    planes = max(1, chunk_rows // max(points_per_plane * rows_per_point, 1))
    with open(path, "wb") as stream:
        stream.write(header.encode() + eol)
        for i0 in range(0, nx, planes):
            i1 = min(nx, i0 + planes)
            block = np.ascontiguousarray(data[i0:i1], dtype=np.float64).reshape(-1, nc)
            point = np.arange(i0 * points_per_plane, i1 * points_per_plane, dtype=np.int64)
            if indexed:
                row = np.repeat(point, nc) * nc + np.tile(np.arange(nc, dtype=np.int64), len(point))
                values = [block.reshape(-1)]
            else:
                row = point
                values = [block[:, c] for c in range(nc)]
            index = np.unravel_index(row, dims)
            parts = [_format_uint(np.asarray(ix) + 1, index_width) for ix in index]
            parts += [_format_es(v, digits, exponent_digits, exponent_char) for v in values]
            if trailing_space:
                parts.append(np.full((len(row), 1), 32, dtype=np.uint8))
            parts.append(np.tile(np.frombuffer(eol, dtype=np.uint8), (len(row), 1)))
            stream.write(memoryview(np.ascontiguousarray(np.hstack(parts))))
    return path
