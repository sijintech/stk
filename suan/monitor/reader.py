"""Read monitoring events by byte offset (standard library only).

Only complete ``\\n``-terminated lines are consumed, so a line being appended is left for
the next read. Lines that are not valid events, or longer than 16 KiB, are skipped and
reported by byte offset. The file is reopened on every call because NFS only guarantees
fresh data on open. Events keep non-finite numbers as the strings ``"NaN"``/``"Inf"``/
``"-Inf"``, so results can be sent as strict JSON.
"""

import errno
import os
import stat

from .events import MAX_LINE, READ_LIMIT, TAIL_WINDOW, EventError, decode_line

SCAN_CHUNK = 64 * 1024
SCAN_LIMIT = READ_LIMIT  # bytes of one oversized line skipped per call, so a call's work stays bounded


def _open(path):
    """Open an events file for reading, or return None when it does not exist."""
    flags = (os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
             | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0))
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        return None
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise ValueError("The events file must not be a symbolic link") from exc
        raise
    stream = os.fdopen(fd, "rb")
    if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
        stream.close()
        raise ValueError("The events file is not a regular file")
    return stream


def _integer(value):
    return not isinstance(value, bool) and isinstance(value, int)


def read_events(path, offset=0, limit=READ_LIMIT):
    """Events from whole lines starting at byte ``offset``, reading at most ``limit`` bytes.

    Returns ``{"events", "offset", "next_offset", "size", "invalid": [{"offset", "reason"}]}``
    where ``next_offset`` is the byte after the last whole line consumed. A single line
    longer than ``limit`` is still returned whole, so every call makes progress. A
    missing file reads as empty; an offset beyond the file size is a ValueError.
    """
    if not _integer(offset) or not _integer(limit) or offset < 0 or not 1 <= limit <= READ_LIMIT:
        raise ValueError("Invalid events range")
    result = {"events": [], "offset": offset, "next_offset": offset, "size": 0, "invalid": []}
    stream = _open(path)
    if stream is None:
        return result
    with stream:
        size = os.fstat(stream.fileno()).st_size
        result["size"] = size
        if offset > size:
            raise ValueError("Offset exceeds events size")
        stream.seek(offset)
        data = stream.read(min(limit, size - offset))

        def take(line, at):
            try:
                result["events"].append(decode_line(line))
            except EventError as exc:
                result["invalid"].append({"offset": at, "reason": str(exc)})

        end = 0
        while True:
            newline = data.find(b"\n", end)
            if newline < 0:
                break
            take(data[end:newline + 1], offset + end)
            end = newline + 1
        if end == 0 and offset + len(data) < size:
            # No whole line fits in the limit: return the first line alone, or skip it when oversized.
            if len(data) <= MAX_LINE:
                data += stream.read(MAX_LINE + 1 - len(data))
            newline = data.find(b"\n")
            if 0 <= newline < MAX_LINE:
                take(data[:newline + 1], offset)
                end = newline + 1
            elif newline >= 0:
                result["invalid"].append({"offset": offset, "reason": f"Line exceeds {MAX_LINE} bytes"})
                end = newline + 1
            elif len(data) > MAX_LINE:
                # An oversized line: skip to its newline, scanning at most SCAN_LIMIT bytes per call.
                position = offset + len(data)
                stream.seek(position)
                while position - offset < SCAN_LIMIT:
                    chunk = stream.read(min(SCAN_CHUNK, SCAN_LIMIT - (position - offset)))
                    if not chunk:
                        break  # it may still be growing; it is skipped once it ends
                    found = chunk.find(b"\n")
                    if found >= 0:
                        end = position + found + 1 - offset
                        break
                    position += len(chunk)
                else:
                    end = position - offset  # garbage however it ends: skip what was scanned
                if end:
                    result["invalid"].append({"offset": offset, "reason": f"Line exceeds {MAX_LINE} bytes"})
            # Otherwise the last line is still incomplete; a later read takes it.
        result["next_offset"] = offset + end
        result["size"] = max(size, offset + end)  # the file may have grown while it was read
    return result


def read_all(path, offset=0):
    """Every whole line from ``offset`` to the current end, in the ``read_events`` structure."""
    total = read_events(path, offset)
    while total["next_offset"] < total["size"]:
        more = read_events(path, total["next_offset"])
        if more["next_offset"] == total["next_offset"]:
            break
        total["events"] += more["events"]
        total["invalid"] += more["invalid"]
        total.update(next_offset=more["next_offset"], size=more["size"])
    return total


def monitor_summary(path, window=TAIL_WINDOW):
    """``{"events_size", "last_progress", "last_ts"}`` from the last ``window`` bytes, or None without a file.

    ``last_progress`` is the data of the last ``progress`` event in that window (None when
    there is none there) and ``last_ts`` the ``ts`` of the last valid event.
    """
    stream = _open(path)
    if stream is None:
        return None
    with stream:
        size = os.fstat(stream.fileno()).st_size
        start = max(0, size - window)
        stream.seek(start)
        data = stream.read(size - start)
    lines = data.split(b"\n")[:-1]
    if start:
        lines = lines[1:]
    summary = {"events_size": size, "last_progress": None, "last_ts": None}
    for line in reversed(lines):
        try:
            event = decode_line(line)
        except EventError:
            continue
        if summary["last_ts"] is None:
            summary["last_ts"] = event["ts"]
        if event["type"] == "progress":
            summary["last_progress"] = event["data"]
            break
    return summary
