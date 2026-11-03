"""Pinned directory handles for private file reception and absent-target publication.

All descendant operations use one validated component relative to an open parent,
including Windows NtCreateFile RootDirectory. Path.resolve plus ordinary open is
not used as a substitute for an anchored operation. No network or authority lives
here; callers must hold their current, short acceptance lease.
"""
from __future__ import annotations

import ctypes
import errno
import os
from pathlib import Path
import stat
import sys

from .manifests import portable_name


class FileStorageError(OSError):
    """A path-free local storage failure; never serialize raw OS exceptions."""


def _component(name):
    if type(name) is not str or "/" in name:
        raise FileStorageError("Expected one portable file name")
    # Prefix permits the internal receipt name without relaxing wire manifests.
    portable_name("root/" + name)
    return name


def _linked(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _identity(info):
    return (info.st_dev, info.st_ino)


class Directory:
    """An explicitly opened ordinary directory, never an implicit path resolver."""

    def __init__(self, handle, path, identity):
        self._handle, self._path, self.identity = handle, Path(path), identity

    def __repr__(self):
        return "<PeerFileDirectory>"

    @classmethod
    def open(cls, path):
        path = Path(path)
        if not path.is_absolute() or ".." in path.parts or "\0" in str(path):
            raise FileStorageError("Expected an absolute local directory")
        if os.name == "nt":
            return _windows_root(path)
        root = path.anchor
        handle = os.open(root, os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0))
        result = cls(handle, root, _identity(os.fstat(handle)))
        try:
            for part in path.parts[1:]:
                child = result.child(part)
                result.close()
                result = child
            result.check()
            return result
        except BaseException:
            result.close()
            raise

    def check(self):
        if self._handle is None:
            raise FileStorageError("File directory is closed")
        if os.name == "nt":
            current, attributes = _windows_info(self._handle)
            if attributes & 0x400 or not attributes & 0x10:
                raise FileStorageError("File directory is no longer ordinary")
        else:
            info = os.fstat(self._handle)
            current = _identity(info)
            if not stat.S_ISDIR(info.st_mode):
                raise FileStorageError("File directory is no longer ordinary")
        if os.name == "nt":
            named, attributes = _windows_absolute_info(self._path)
            linked = bool(attributes & 0x400)
        else:
            info = self._path.lstat()
            named, linked = _identity(info), _linked(info)
        if linked or current != self.identity or named != self.identity:
            raise FileStorageError("File directory identity changed")

    def child(self, name, *, create=False, exclusive=False):
        name = _component(name)
        self.check()
        if os.name == "nt":
            handle = _windows_relative(self._handle, name, directory=True, create=create,
                                       exclusive=exclusive)
            identity, attributes = _windows_info(handle)
            if attributes & 0x400 or not attributes & 0x10:
                _windows_close(handle)
                raise FileStorageError("File directory must not be a reparse point")
        else:
            if create:
                try:
                    os.mkdir(name, mode=0o700, dir_fd=self._handle)
                    os.fsync(self._handle)
                except FileExistsError:
                    if exclusive:
                        raise
            handle = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                             | getattr(os, "O_CLOEXEC", 0), dir_fd=self._handle)
            identity = _identity(os.fstat(handle))
        result = type(self)(handle, self._path / name, identity)
        try:
            self.check()
            result.check()
            return result
        except BaseException:
            result.close()
            raise

    def file(self, name, *, create=False, write=False):
        """Open a bounded caller-selected file; create is always create-if-absent."""
        name = _component(name)
        self.check()
        if create and not write:
            raise FileStorageError("Creating a file requires explicit write access")
        if os.name == "nt":
            import msvcrt
            handle = _windows_relative(self._handle, name, directory=False, create=create,
                                       exclusive=True, write=write)
            try:
                _, attributes = _windows_info(handle)
                if attributes & (0x400 | 0x10):
                    raise FileStorageError("Transfer files must be ordinary files")
                fd = msvcrt.open_osfhandle(handle, os.O_BINARY | os.O_NOINHERIT
                                          | (os.O_RDWR if write else os.O_RDONLY))
            except BaseException:
                _windows_close(handle)
                raise
        else:
            flags = (os.O_RDWR if write else os.O_RDONLY) | os.O_NOFOLLOW | os.O_NONBLOCK
            flags |= getattr(os, "O_CLOEXEC", 0)
            if create:
                flags |= os.O_CREAT | os.O_EXCL
            fd = os.open(name, flags, mode=0o600, dir_fd=self._handle)
        try:
            opened = os.fstat(fd)
            if os.name == "nt":
                import msvcrt
                opened_identity, opened_attributes = _windows_info(msvcrt.get_osfhandle(fd))
                named_handle = _windows_relative(self._handle, name, directory=False)
                try:
                    named_identity, named_attributes = _windows_info(named_handle)
                finally:
                    _windows_close(named_handle)
                linked = bool((opened_attributes | named_attributes) & 0x400)
            else:
                named = (self._path / name).lstat()
                opened_identity, named_identity, linked = _identity(opened), _identity(named), _linked(named)
            if not stat.S_ISREG(opened.st_mode) or linked or opened_identity != named_identity:
                raise FileStorageError("Transfer files must be ordinary files with a stable identity")
            self.check()
            return os.fdopen(fd, "r+b" if write else "rb", buffering=0)
        except BaseException:
            os.close(fd)
            raise

    def sync(self):
        self.check()
        if os.name != "nt":
            os.fsync(self._handle)
        # Windows file payloads use FlushFileBuffers through os.fsync(file.fd).
        # Renames below use the OS no-replace operation; no directory-fsync claim.

    def publish(self, source, target, *, expected_identity):
        """Rename one staged directory within this parent without replacing a target.

        Missing native no-replace support fails closed; there is no check-then-
        rename fallback. A caller journals intent first and treats a lost result
        or a failing post-operation identity check as uncertain.
        """
        source, target = _component(source), _component(target)
        if source == target:
            raise FileStorageError("Publication needs a distinct destination")
        self.check()
        with self.child(source) as staged:
            if tuple(expected_identity) != staged.identity:
                raise FileStorageError("Staged directory identity changed")
            if os.name == "nt":
                _windows_publish(self._handle, source, target, staged.identity)
            else:
                library = ctypes.CDLL(None, use_errno=True)
                # Apple's bsd/sys/stdio.h defines RENAME_EXCL=4; Linux RENAME_NOREPLACE=1.
                symbol, flag = (("renameatx_np", 4) if sys.platform == "darwin" else ("renameat2", 1))
                function = getattr(library, symbol, None)
                if function is None:
                    raise FileStorageError("Atomic absent-target publication is unavailable")
                function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                                     ctypes.c_char_p, ctypes.c_uint]
                function.restype = ctypes.c_int
                if function(self._handle, os.fsencode(source), self._handle, os.fsencode(target), flag):
                    code = ctypes.get_errno()
                    if code in (errno.EEXIST, errno.ENOTEMPTY):
                        raise FileExistsError("Publication target already exists")
                    raise FileStorageError("Atomic file publication failed")
            self.sync()
            with self.child(target) as published:
                if published.identity != staged.identity:
                    raise FileStorageError("Published directory identity changed")

    def close(self):
        handle, self._handle = self._handle, None
        if handle is not None:
            if os.name == "nt":
                _windows_close(handle)
            else:
                os.close(handle)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def _windows_close(handle):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    close = kernel.CloseHandle
    close.argtypes, close.restype = [ctypes.c_void_p], ctypes.c_int
    close(handle)


def _windows_info(handle):
    from ctypes import wintypes as w
    class FileId(ctypes.Structure):
        _fields_ = [("volume", ctypes.c_uint64), ("identifier", w.BYTE * 16)]
    class Attributes(ctypes.Structure):
        _fields_ = [("attributes", w.DWORD), ("tag", w.DWORD)]
    query = ctypes.WinDLL("kernel32", use_last_error=True).GetFileInformationByHandleEx
    query.argtypes, query.restype = [w.HANDLE, ctypes.c_int, w.LPVOID, w.DWORD], w.BOOL
    identity, attributes = FileId(), Attributes()
    if (not query(handle, 18, ctypes.byref(identity), ctypes.sizeof(identity))
            or not query(handle, 9, ctypes.byref(attributes), ctypes.sizeof(attributes))):
        raise FileStorageError("Cannot verify transfer file identity")
    # Do not mix legacy 64-bit FileIndex or CPython's version-dependent stat IDs.
    return (int(identity.volume), int.from_bytes(bytes(identity.identifier), "little")), attributes.attributes


def _windows_drive(path):
    from ctypes import wintypes as w
    if len(path.drive) != 2 or path.drive[1] != ":":
        raise FileStorageError("File transfers require a local Windows drive")
    create = ctypes.WinDLL("kernel32", use_last_error=True).CreateFileW
    create.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, w.LPVOID, w.DWORD, w.DWORD, w.HANDLE]
    create.restype = w.HANDLE
    handle = create(path.anchor, 0x100000 | 0x80 | 0x20 | 0x1, 7, None, 3,
                    0x02000000 | 0x00200000, None)
    if handle in (None, w.HANDLE(-1).value):
        raise FileStorageError("Cannot open the local drive")
    return handle


def _windows_absolute_info(path):
    """Reopen the named path by native relative handles, never through junctions."""
    handle = _windows_drive(path)
    try:
        identity, attributes = _windows_info(handle)
        if attributes & 0x400 or not attributes & 0x10:
            raise FileStorageError("Drive root must be an ordinary directory")
        for part in path.parts[1:]:
            child = _windows_relative(handle, _component(part), directory=True)
            _windows_close(handle)
            handle = child
            identity, attributes = _windows_info(handle)
            if attributes & 0x400 or not attributes & 0x10:
                raise FileStorageError("File directory must not contain reparse points")
        return identity, attributes
    finally:
        _windows_close(handle)


def _windows_root(path):
    handle = _windows_drive(path)
    try:
        identity, attributes = _windows_info(handle)
        if attributes & 0x400 or not attributes & 0x10:
            raise FileStorageError("Drive root must be an ordinary directory")
        result = Directory(handle, path.anchor, identity)
    except BaseException:
        _windows_close(handle)
        raise
    try:
        for part in path.parts[1:]:
            child = result.child(part)
            result.close()
            result = child
        result.check()
        return result
    except BaseException:
        result.close()
        raise


def _windows_private_descriptor():
    """Protected current-user DACL supplied at creation, before any bytes exist."""
    from ctypes import wintypes as w
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    security = ctypes.WinDLL("advapi32", use_last_error=True)
    process = kernel.GetCurrentProcess
    process.argtypes, process.restype = [], w.HANDLE
    open_token = security.OpenProcessToken
    open_token.argtypes, open_token.restype = [w.HANDLE, w.DWORD, ctypes.POINTER(w.HANDLE)], w.BOOL
    token = w.HANDLE()
    if not open_token(process(), 0x8, ctypes.byref(token)):
        raise FileStorageError("Cannot establish private transfer ownership")
    query = security.GetTokenInformation
    query.argtypes, query.restype = [w.HANDLE, ctypes.c_int, w.LPVOID, w.DWORD, ctypes.POINTER(w.DWORD)], w.BOOL
    size = w.DWORD()
    try:
        query(token, 1, None, 0, ctypes.byref(size))
        if not 1 <= size.value <= 65536:
            raise FileStorageError("Cannot establish private transfer ownership")
        buffer = ctypes.create_string_buffer(size.value)
        if not query(token, 1, buffer, size.value, ctypes.byref(size)):
            raise FileStorageError("Cannot establish private transfer ownership")
        # TOKEN_USER begins with SID_AND_ATTRIBUTES, whose first member is a SID pointer.
        sid = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p)).contents.value
        convert_sid = security.ConvertSidToStringSidW
        convert_sid.argtypes, convert_sid.restype = [w.LPVOID, ctypes.POINTER(w.LPWSTR)], w.BOOL
        text = w.LPWSTR()
        if not convert_sid(sid, ctypes.byref(text)):
            raise FileStorageError("Cannot establish private transfer ownership")
        try:
            descriptor = w.LPVOID()
            convert = security.ConvertStringSecurityDescriptorToSecurityDescriptorW
            convert.argtypes = [w.LPCWSTR, w.DWORD, ctypes.POINTER(w.LPVOID), ctypes.POINTER(w.DWORD)]
            convert.restype = w.BOOL
            if not convert("D:P(A;OICI;FA;;;" + text.value + ")", 1, ctypes.byref(descriptor), None):
                raise FileStorageError("Cannot establish private transfer ownership")
            return descriptor
        finally:
            _windows_local_free(text)
    finally:
        _windows_close(token)


def _windows_local_free(pointer):
    function = ctypes.WinDLL("kernel32", use_last_error=True).LocalFree
    function.argtypes, function.restype = [ctypes.c_void_p], ctypes.c_void_p
    function(ctypes.cast(pointer, ctypes.c_void_p))


def _windows_relative(parent, name, *, directory, create=False, exclusive=False, write=False, delete=False):
    # Primary contract: learn.microsoft.com/windows/win32/api/winternl/nf-winternl-ntcreatefile
    from ctypes import wintypes as w
    class Unicode(ctypes.Structure):
        _fields_ = [("length", w.USHORT), ("maximum", w.USHORT), ("buffer", w.LPWSTR)]
    class Attributes(ctypes.Structure):
        _fields_ = [("length", w.ULONG), ("root", w.HANDLE), ("name", ctypes.POINTER(Unicode)),
                    ("flags", w.ULONG), ("security", w.LPVOID), ("qos", w.LPVOID)]
    class Status(ctypes.Structure):
        _fields_ = [("status", ctypes.c_void_p), ("information", ctypes.c_size_t)]
    buffer = ctypes.create_unicode_buffer(name)
    length = len(name.encode("utf-16-le"))
    string = Unicode(length, length + 2, ctypes.cast(buffer, w.LPWSTR))
    descriptor = _windows_private_descriptor() if create else None
    attributes = Attributes(ctypes.sizeof(Attributes), parent, ctypes.pointer(string), 0x40, descriptor, None)
    handle, status = w.HANDLE(), Status()
    function = ctypes.WinDLL("ntdll").NtCreateFile
    function.argtypes = [ctypes.POINTER(w.HANDLE), w.DWORD, ctypes.POINTER(Attributes),
        ctypes.POINTER(Status), w.LPVOID, w.ULONG, w.ULONG, w.ULONG, w.ULONG, w.LPVOID, w.ULONG]
    function.restype = ctypes.c_long
    access = 0x100000 | 0x80 | (0x20 | 0x1 if directory else 0x1)
    if write and not directory:
        access |= 0x2
    if delete:
        access |= 0x10000
    disposition = (2 if exclusive else 3) if create else 1  # CREATE / OPEN_IF / OPEN
    options = 0x00200000 | 0x20 | (0x1 if directory else 0x40)
    try:
        result = function(ctypes.byref(handle), access, ctypes.byref(attributes), ctypes.byref(status),
                          None, 0x10 if directory else 0x80, 7, disposition, options, None, 0)
    finally:
        if descriptor is not None:
            _windows_local_free(descriptor)
    if result < 0:
        code = result & 0xFFFFFFFF
        if code == 0xC0000035:
            raise FileExistsError("Transfer target already exists")
        if code in (0xC0000034, 0xC000003A):
            raise FileNotFoundError("Transfer file is missing")
        raise FileStorageError("Anchored transfer file access failed")
    return handle.value


def _windows_publish(parent, source, target, expected_identity):
    from ctypes import wintypes as w
    source_handle = _windows_relative(parent, source, directory=True, delete=True)
    try:
        identity, attributes = _windows_info(source_handle)
        if identity != expected_identity or attributes & 0x400:
            raise FileStorageError("Staged directory identity changed")
        class Rename(ctypes.Structure):
            _fields_ = [("flags", w.DWORD), ("root", w.HANDLE), ("length", w.DWORD), ("name", w.WCHAR * 1)]
        encoded = target.encode("utf-16-le")
        buffer = ctypes.create_string_buffer(Rename.name.offset + len(encoded))
        value = ctypes.cast(buffer, ctypes.POINTER(Rename)).contents
        value.flags, value.root, value.length = 0, parent, len(encoded)
        ctypes.memmove(ctypes.addressof(buffer) + Rename.name.offset, encoded, len(encoded))
        function = ctypes.WinDLL("kernel32", use_last_error=True).SetFileInformationByHandle
        function.argtypes, function.restype = [w.HANDLE, ctypes.c_int, w.LPVOID, w.DWORD], w.BOOL
        if not function(source_handle, 3, buffer, len(buffer)):
            if ctypes.get_last_error() in (80, 183):
                raise FileExistsError("Publication target already exists")
            raise FileStorageError("Atomic file publication failed")
    finally:
        _windows_close(source_handle)


__all__ = ["Directory", "FileStorageError"]
