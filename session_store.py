"""Persist sessions only when the operating system can seal them securely."""

import ctypes
import hashlib
import json
import os
import sys
from pathlib import Path

MAC_SERVICE = "cloud.myshelf.mymovielist.session"
MAX_SESSION_BYTES = 65536


def mac_keychain():
    """Select only Apple's Keychain; never fall back to a file or plugin backend."""
    from keyring.backends.macOS import Keyring

    backend = Keyring()
    if backend.priority <= 0:
        raise OSError("macOS Keychain is unavailable.")
    return backend


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
        # The app's canonical data directory distinguishes release, dev and QA
        # sessions without placing a token or an email address in the item name.
        self.mac_account = hashlib.sha256(
            str(self.path.parent.resolve()).encode("utf-8")
        ).hexdigest()

    @property
    def persistent(self):
        return self.android or sys.platform in ("win32", "darwin")

    @property
    def uses_keychain(self):
        return sys.platform == "darwin" and not self.android

    def keychain_call(self, action, value=None):
        try:
            backend = mac_keychain()
            if action == "save":
                backend.set_password(MAC_SERVICE, self.mac_account, value)
            elif action == "load":
                return backend.get_password(MAC_SERVICE, self.mac_account)
            elif (
                action == "clear"
                and backend.get_password(MAC_SERVICE, self.mac_account) is not None
            ):
                backend.delete_password(MAC_SERVICE, self.mac_account)
        except Exception:  # noqa: BLE001 -- SDK errors can contain credential details.
            raise OSError(
                "The operating system could not protect the session."
            ) from None

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
        if self.uses_keychain:
            raw = json.dumps(value)
            if len(raw.encode("utf-8")) > MAX_SESSION_BYTES:
                raise OSError("The session is too large to store securely.")
            self.keychain_call("save", raw)
        elif self.persistent:
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
        if self.uses_keychain:
            try:
                raw = self.keychain_call("load")
                if raw is None or len(raw.encode("utf-8")) > MAX_SESSION_BYTES:
                    return None
                value = json.loads(raw)
                return value if isinstance(value, dict) else None
            except (OSError, ValueError, TypeError):
                # A locked/unavailable Keychain requires login, never a library reset.
                return None
        if not self.persistent or not self.path.exists():
            return None
        try:
            raw = self.path.read_bytes()
            if len(raw) > MAX_SESSION_BYTES:
                return None
            return json.loads(self.seal(raw, True))
        except (OSError, ValueError, RuntimeError):
            # An unreadable OS-bound session requires login, not a library reset.
            return None

    def clear(self):
        self.memory = None
        if self.uses_keychain:
            self.keychain_call("clear")
        self.path.unlink(missing_ok=True)
