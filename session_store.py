"""Persist sessions only when the operating system can seal them securely."""

import ctypes
import json
import os
import sys
from pathlib import Path


def windows_seal(data, decrypt=False):
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(data)
    incoming = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    outgoing = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if decrypt:
        function = crypt.CryptUnprotectData
        function.argtypes = [
            ctypes.POINTER(Blob),
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(Blob),
        ]
        arguments = (
            ctypes.byref(incoming),
            None,
            None,
            None,
            None,
            1,
            ctypes.byref(outgoing),
        )
    else:
        function = crypt.CryptProtectData
        function.argtypes = [
            ctypes.POINTER(Blob),
            wintypes.LPCWSTR,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(Blob),
        ]
        arguments = (
            ctypes.byref(incoming),
            "MyMovieList cloud session",
            None,
            None,
            None,
            1,
            ctypes.byref(outgoing),
        )
    function.restype = wintypes.BOOL
    if not function(*arguments):
        raise OSError("The operating system could not protect the session.")
    try:
        return ctypes.string_at(outgoing.data, outgoing.size)
    finally:
        kernel.LocalFree(outgoing.data)


class SessionStore:
    def __init__(self, folder, android=False):
        self.path = Path(folder) / "cloud-session.sealed"
        self.android = android
        self.memory = None

    @property
    def persistent(self):
        return self.android or sys.platform == "win32"

    def seal(self, raw, decrypt=False):
        if self.android:
            try:
                from java import jclass

                helper = jclass("com.moviewatchlist.CloudSessionStore")
                return (
                    str(helper.open(raw.decode("ascii"))).encode("utf-8")
                    if decrypt
                    else str(helper.seal(raw.decode("utf-8"))).encode("ascii")
                )
            except Exception:  # noqa: BLE001 -- Java bridge failures must be redacted at this boundary.
                raise OSError(
                    "The operating system could not protect the session."
                ) from None
        return windows_seal(raw, decrypt)

    def save(self, value):
        if self.persistent:
            raw = self.seal(json.dumps(value).encode("utf-8"))
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_suffix(".tmp")
            try:
                temp.write_bytes(raw)
                os.replace(temp, self.path)
            finally:
                temp.unlink(missing_ok=True)
        self.memory = dict(value)

    def load(self):
        if self.memory is not None:
            return dict(self.memory)
        if not self.persistent or not self.path.exists():
            return None
        try:
            raw = self.path.read_bytes()
            if len(raw) > 65536:
                return None
            return json.loads(self.seal(raw, True))
        except (OSError, ValueError, RuntimeError):
            # An unreadable OS-bound session requires login, not a library reset.
            return None

    def clear(self):
        self.memory = None
        self.path.unlink(missing_ok=True)
