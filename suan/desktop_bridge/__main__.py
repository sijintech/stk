"""``python -m suan.desktop_bridge --stdio [--state-dir DIR] [--cache-dir DIR] [--strict]``.

stdout carries only protocol lines: before anything else runs, the protocol stream is moved to a
private duplicate of file descriptor 1, and descriptor 1 itself (plus ``sys.stdout`` and logging)
is pointed at stderr, so stray ``print`` calls, library output and child processes can never
corrupt the NDJSON stream. Likewise requests are read from a private duplicate of descriptor 0,
which is pointed at the null device, so child processes never see the protocol input. The process
exits when stdin reaches EOF (or on ``shutdown``).
"""
import argparse
import logging
import os
import sys


def _protocol_stdout():
    """A binary writer on a duplicate of fd 1; fd 1 and sys.stdout then point at stderr."""
    sys.stdout.flush()
    fd = os.dup(1)
    if os.name == "nt":
        import msvcrt
        msvcrt.setmode(fd, os.O_BINARY)
    os.dup2(2, 1)
    if os.name == "nt":
        # Child processes inherit the Win32 standard handle, not the C runtime descriptor.
        try:
            import ctypes
            import msvcrt
            ctypes.windll.kernel32.SetStdHandle(-11, msvcrt.get_osfhandle(1))  # STD_OUTPUT_HANDLE
        except (OSError, AttributeError, ImportError):
            pass
    sys.stdout = sys.stderr
    return os.fdopen(fd, "wb", buffering=0)


def _protocol_stdin():
    """A binary reader on a duplicate of fd 0; fd 0 and sys.stdin then read from the null device.

    Child processes must not inherit the protocol pipe: they could consume requests, and on Windows
    a child touching a synchronous pipe that the bridge is blocked reading hangs at startup.
    """
    fd = os.dup(0)
    if os.name == "nt":
        import msvcrt
        msvcrt.setmode(fd, os.O_BINARY)
    null = os.open(os.devnull, os.O_RDONLY)
    os.dup2(null, 0)
    os.close(null)
    if os.name == "nt":
        try:
            import ctypes
            import msvcrt
            ctypes.windll.kernel32.SetStdHandle(-10, msvcrt.get_osfhandle(0))  # STD_INPUT_HANDLE
        except (OSError, AttributeError, ImportError):
            pass
    sys.stdin = open(os.devnull, encoding="utf-8")
    return os.fdopen(fd, "rb")


def _exit():
    for stream in (sys.stderr, sys.__stderr__):
        try:
            stream.flush()
        except (OSError, ValueError, AttributeError):
            pass
    os._exit(0)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m suan.desktop_bridge",
                                     description="STK desktop bridge: NDJSON over stdin/stdout.")
    parser.add_argument("--stdio", action="store_true", required=True, help="Speak the protocol on stdin/stdout")
    parser.add_argument("--state-dir", help="Bridge state (profiles of paired hubs, transfer journals); default "
                        "$STK_DESKTOP_BRIDGE_DIR or ~/.stk/desktop-bridge")
    parser.add_argument("--cache-dir", help="Blob, download and graph cache; default <state-dir>/cache")
    parser.add_argument("--strict", action="store_true", default=os.environ.get("STK_BRIDGE_STRICT") == "1",
                        help="Validate every outgoing message against the protocol schema")
    args = parser.parse_args(argv)
    writer = _protocol_stdout()
    reader = _protocol_stdin()
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING,
                        format="stk-desktop-bridge %(levelname)s %(name)s: %(message)s")
    from .server import Bridge
    bridge = Bridge(args.state_dir, args.cache_dir, writer=writer, strict=args.strict,
                    on_exit=_exit)
    try:
        bridge.serve(reader)
    except KeyboardInterrupt:
        bridge.shutdown()
    try:
        writer.flush()
    except OSError:
        pass
    # Daemon threads (subscriptions, transfers paused at a chunk boundary) end with the process.
    _exit()


if __name__ == "__main__":
    main()
