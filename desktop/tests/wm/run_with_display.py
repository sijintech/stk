#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Run a command against a private, throw-away display server.

    run_with_display.py --server xvfb|weston --workdir DIR [--sysroot DIR] -- CMD...

* ``xvfb``: Xvfb with ``-nolisten tcp`` (unix sockets only), an MIT-MAGIC-COOKIE
  Xauthority file and a display number chosen by the server (``-displayfd``).
* ``weston``: weston's headless backend (pixman renderer, kiosk shell, or the desktop shell
  with ``--weston-shell desktop`` for normal, non-fullscreen toplevels) with its own
  ``XDG_RUNTIME_DIR`` (mode 0700) under DIR; the socket lives there.

The server never binds a TCP port (verified through /proc after start-up; the test
fails if it did) and is stopped when the command ends. Binaries come from PATH or,
when missing there, from the user sysroot (``fetch-sysroot.sh --with-test-servers``).
Exit code: the command's, or 77 (ctest SKIP_RETURN_CODE) when the server is not
available.
"""

from __future__ import annotations

import argparse
import os
import secrets
import shutil
import signal
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path

SKIP = 77


def skip(msg: str) -> int:
    print(f"SKIP: {msg}", flush=True)
    return SKIP


def find_binary(name: str, sysroot: Path | None) -> tuple[Path | None, bool]:
    """Return (path, from_sysroot)."""
    found = shutil.which(name)
    if found:
        return Path(found), False
    if sysroot:
        cand = sysroot / "usr" / "bin" / name
        if cand.is_file() and os.access(cand, os.X_OK):
            return cand, True
    return None, False


def sysroot_env(env: dict, sysroot: Path) -> None:
    libdir = sysroot / "usr" / "lib" / "x86_64-linux-gnu"
    paths = [str(libdir), str(libdir / "weston")]
    if env.get("LD_LIBRARY_PATH"):
        paths.append(env["LD_LIBRARY_PATH"])
    env["LD_LIBRARY_PATH"] = ":".join(paths)


def tcp_listen_inodes() -> set[str]:
    inodes = set()
    for table in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            with open(table) as f:
                next(f)
                for line in f:
                    cols = line.split()
                    if len(cols) > 9 and cols[3] == "0A":  # TCP_LISTEN
                        inodes.add(cols[9])
        except OSError:
            pass
    return inodes


def process_listens_on_tcp(pid: int) -> bool:
    """True when `pid` owns a listening TCP socket (IPv4 or IPv6)."""
    listening = tcp_listen_inodes()
    try:
        for fd in os.listdir(f"/proc/{pid}/fd"):
            try:
                target = os.readlink(f"/proc/{pid}/fd/{fd}")
            except OSError:
                continue
            if target.startswith("socket:[") and target[8:-1] in listening:
                return True
    except OSError:
        pass
    return False


def write_xauthority(path: Path, cookie: bytes) -> None:
    """One FamilyWild entry with an empty display number: Xlib matches it for any host and
    display, and the server only uses the protocol name and cookie."""

    def field(b: bytes) -> bytes:
        return struct.pack(">H", len(b)) + b

    entry = struct.pack(">H", 0xFFFF) + field(b"") + field(b"") + \
        field(b"MIT-MAGIC-COOKIE-1") + field(cookie)
    path.write_bytes(entry)
    path.chmod(0o600)


def patched_xvfb(xvfb: Path, sysroot: Path, workdir: Path) -> Path | None:
    """Xvfb runs `/usr/bin/xkbcomp`. When that is missing but the sysroot has xkbcomp, run
    a copy of Xvfb whose compiled-in XKB binary directory points to ./xkbbin instead
    (same string length, relative to the server's working directory)."""
    xkbcomp = sysroot / "usr" / "bin" / "xkbcomp"
    if Path("/usr/bin/xkbcomp").exists() or not xkbcomp.exists():
        return xvfb
    data = xvfb.read_bytes()
    old, new = b"\x00/usr/bin\x00", b"\x00./xkbbin\x00"
    if data.count(old) != 1:
        return None
    copy = workdir / "Xvfb-xkbbin"
    copy.write_bytes(data.replace(old, new))
    copy.chmod(0o700)
    bindir = workdir / "xkbbin"
    bindir.mkdir(exist_ok=True)
    link = bindir / "xkbcomp"
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(xkbcomp)
    return copy


def start_xvfb(args, env: dict, workdir: Path):
    xvfb, from_sysroot = find_binary("Xvfb", args.sysroot)
    if not xvfb:
        return None, "Xvfb not found (apt install xvfb, or fetch-sysroot.sh --with-test-servers)"
    cmd_env = dict(os.environ)
    extra = []
    if from_sysroot:
        sysroot_env(cmd_env, args.sysroot)
        patched = patched_xvfb(xvfb, args.sysroot, workdir)
        if not patched:
            return None, "sysroot Xvfb cannot find xkbcomp"
        xvfb = patched
        xkb = args.sysroot / "usr" / "share" / "X11" / "xkb"
        if xkb.is_dir():
            extra += ["-xkbdir", str(xkb)]
    read_fd, write_fd = os.pipe()
    auth = workdir / "Xauthority"
    # Written before start-up: the server loads its cookies from this file when it starts.
    write_xauthority(auth, secrets.token_bytes(16))
    cmd = [str(xvfb), "-displayfd", str(write_fd), "-nolisten", "tcp", "-auth", str(auth),
           "-screen", "0", "1280x800x24", "-dpi", "96", "-nocursor"] + extra
    log = open(workdir / "server.log", "wb")
    proc = subprocess.Popen(cmd, cwd=workdir, env=cmd_env, stdout=log, stderr=subprocess.STDOUT,
                            pass_fds=(write_fd,))
    os.close(write_fd)
    display = b""
    deadline = time.monotonic() + 15
    os.set_blocking(read_fd, False)
    while time.monotonic() < deadline and proc.poll() is None:
        try:
            chunk = os.read(read_fd, 64)
        except BlockingIOError:
            chunk = None
        if chunk:
            display += chunk
            if b"\n" in display:
                break
        elif chunk == b"":
            break
        time.sleep(0.05)
    os.close(read_fd)
    if not display.strip():
        proc.kill()
        proc.wait()
        return None, "Xvfb did not start:\n" + (workdir / "server.log").read_text(errors="replace")[-2000:]
    disp = ":" + display.decode().strip()
    env["DISPLAY"] = disp
    env["XAUTHORITY"] = str(auth)
    env.pop("WAYLAND_DISPLAY", None)
    # No Wayland socket in this runtime dir, so GHOST falls back to X11.
    rt = workdir / "rt"
    rt.mkdir(mode=0o700, exist_ok=True)
    env["XDG_RUNTIME_DIR"] = str(rt)
    return proc, f"Xvfb {disp}"


def start_weston(args, env: dict, workdir: Path):
    weston, from_sysroot = find_binary("weston", args.sysroot)
    if not weston:
        return None, "weston not found (apt install weston, or fetch-sysroot.sh --with-test-servers)"
    cmd_env = dict(os.environ)
    if from_sysroot:
        sysroot_env(cmd_env, args.sysroot)
        lib = args.sysroot / "usr" / "lib" / "x86_64-linux-gnu"
        modules = {
            "headless-backend.so": lib / "libweston-14" / "headless-backend.so",
            "kiosk-shell.so": lib / "weston" / "kiosk-shell.so",
            "desktop-shell.so": lib / "weston" / "desktop-shell.so",
        }
        cmd_env["WESTON_MODULE_MAP"] = ";".join(f"{k}={v}" for k, v in modules.items())
    rt = workdir / "xdg"
    rt.mkdir(mode=0o700, exist_ok=True)
    rt.chmod(0o700)
    sock = "stk-wl-0"
    if len(str(rt / sock)) >= 100:
        return None, f"runtime dir path too long for a unix socket: {rt}"
    if (rt / sock).exists():
        (rt / sock).unlink()
    cmd_env["XDG_RUNTIME_DIR"] = str(rt)
    cmd_env.pop("DISPLAY", None)
    cmd_env.pop("WAYLAND_DISPLAY", None)
    cmd = [str(weston), "--backend=headless", "--renderer=pixman", f"--socket={sock}",
           "--width=1280", "--height=800", f"--shell={args.weston_shell}", "--idle-time=0"]
    if args.weston_shell == "desktop":
        # The desktop shell starts its panel client; point it at the sysroot copy when the
        # compiled-in libexec path does not exist.
        client = Path("/usr/libexec/weston-desktop-shell")
        if from_sysroot and not client.exists():
            client = args.sysroot / "usr" / "libexec" / "weston-desktop-shell"
        ini = workdir / "weston.ini"
        ini.write_text(f"[shell]\nclient={client}\npanel-position=none\nlocking=false\n")
        cmd.append(f"--config={ini}")
    else:
        cmd.append("--no-config")
    log = open(workdir / "server.log", "wb")
    proc = subprocess.Popen(cmd, cwd=workdir, env=cmd_env, stdout=log, stderr=subprocess.STDOUT)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and proc.poll() is None:
        if (rt / sock).exists():
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.connect(str(rt / sock))
                s.close()
                break
            except OSError:
                pass
        time.sleep(0.05)
    else:
        proc.kill()
        proc.wait()
        return None, "weston did not start:\n" + (workdir / "server.log").read_text(errors="replace")[-2000:]
    env["XDG_RUNTIME_DIR"] = str(rt)
    env["WAYLAND_DISPLAY"] = sock
    env.pop("DISPLAY", None)
    return proc, f"weston (headless) {rt / sock}"


def stop(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--server", choices=("xvfb", "weston"), required=True)
    ap.add_argument("--workdir", type=Path, required=True)
    ap.add_argument("--sysroot", type=Path, default=None)
    ap.add_argument("--timeout", type=float, default=120)
    ap.add_argument("--weston-shell", choices=("kiosk", "desktop"), default="kiosk")
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    args = ap.parse_args()
    cmd = args.cmd[1:] if args.cmd[:1] == ["--"] else args.cmd
    if not cmd:
        ap.error("missing command")
    if not sys.platform.startswith("linux"):
        return skip("display servers are only used on Linux")
    if args.sysroot and not args.sysroot.is_dir():
        args.sysroot = None

    workdir = args.workdir.resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    start = start_xvfb if args.server == "xvfb" else start_weston
    proc, info = start(args, env, workdir)
    if proc is None:
        return skip(info)
    try:
        time.sleep(0.2)
        if process_listens_on_tcp(proc.pid):
            print(f"FAIL: {info} listens on a TCP port; refusing to run", flush=True)
            return 1
        print(f"display: {info} (unix sockets only)", flush=True)
        try:
            return subprocess.run(cmd, env=env, timeout=args.timeout).returncode
        except subprocess.TimeoutExpired:
            print(f"FAIL: command timed out after {args.timeout:g} s", flush=True)
            return 1
    finally:
        stop(proc)


if __name__ == "__main__":
    sys.exit(main())
