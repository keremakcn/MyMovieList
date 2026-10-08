"""Optional accounts over separate local libraries; one bounded background worker."""

import json
import math
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from flask import g, has_request_context
from werkzeug.local import LocalProxy

from account_profile import ProfileStore, validate_profile
from account_username import UsernameStore
from catalog import CatalogService
from cloud_client import CloudError, SupabaseClient
from profile_sharing import SharingStore
from recommendations import Recommender
from session_store import SessionStore
from storage import Database
from sync_store import SyncStore


class CloudWorkspace:
    def __init__(self, app, guest, tmdb):
        self.app, self.guest, self.tmdb = app, guest, tmdb
        self.folder = Path(app.config["DATA_DIR"])
        self.lock = threading.RLock()
        self.auth_lock = threading.Lock()
        self.run_lock = threading.Lock()
        self.epoch = secrets.token_hex(16)
        self.stopped, self.wake = threading.Event(), threading.Event()
        self.thread = None
        self.vault = app.config.get("CLOUD_SESSION_STORE") or SessionStore(
            self.folder, app.config.get("ANDROID_APP", False)
        )
        self.session = self.vault.load()
        self.client = app.config.get("CLOUD_CLIENT")
        config_file = Path(__file__).parent / "supabase" / "project.json"
        try:
            configuration = (
                json.loads(config_file.read_text()) if config_file.exists() else {}
            )
            if not isinstance(configuration, dict):
                raise TypeError("Invalid cloud configuration.")
        except (OSError, ValueError, TypeError):
            configuration = {}
            app.logger.warning(
                "Cloud configuration is unavailable. Local libraries remain available."
            )
        self.ready = (
            app.config.get(
                "CLOUD_ACCOUNTS_READY", configuration.get("accounts_enabled", False)
            )
            is True
        )
        if (
            self.client is None
            and configuration.get("url")
            and configuration.get("publishable_key")
        ):
            try:
                self.client = SupabaseClient(
                    configuration["url"], configuration["publishable_key"]
                )
            except (ValueError, TypeError):
                self.ready = False
                app.logger.warning(
                    "Cloud configuration is invalid. Local libraries remain available."
                )
        self.public_ready = (
            self.ready
            and bool(
                app.config.get(
                    "PUBLIC_PROFILES_READY",
                    configuration.get("public_profiles_enabled", False),
                )
            )
            and all(
                hasattr(self.client, method)
                for method in ("sharing_status", "write_showcase", "public_profile")
            )
        )
        self.selected = None
        selected = guest.query(
            "SELECT value FROM settings WHERE key='cloud_active_account'"
        )
        if selected and selected[0]["value"]:
            try:
                self.selected = str(UUID(selected[0]["value"]))
            except ValueError:
                pass
        try:
            self.session = self.checked_session(self.session, stored=True)
        except (CloudError, ValueError, TypeError):
            self.session = None
        if not self.session or self.session["user_id"] != self.selected:
            self.session = None
        self.libraries = {}
        self.states = {}
        self._library(None)
        if not app.testing and self.ready:
            self.thread = threading.Thread(
                target=self._work, daemon=True, name="private-library-sync"
            )
            self.thread.start()
        self.db = LocalProxy(lambda: self.current().db)
        self.catalog = LocalProxy(lambda: self.current().catalog)
        self.recommender = LocalProxy(lambda: self.current().recommender)

    def _library(self, owner):
        with self.lock:
            if owner not in self.libraries:
                db = (
                    self.guest
                    if owner is None
                    else Database(
                        self.folder / "accounts" / owner / "library.db", owner
                    )
                )
                if owner:
                    db.migrate()
                catalog = CatalogService(
                    db,
                    self.tmdb,
                    background=self.app.config.get(
                        "BACKGROUND_METADATA", not self.app.testing
                    ),
                )
                self.libraries[owner] = SimpleNamespace(
                    owner=owner,
                    db=db,
                    catalog=catalog,
                    recommender=Recommender(db, self.tmdb, catalog),
                    store=SyncStore(db),
                    profile=ProfileStore(db),
                    sharing=SharingStore(db, self.public_ready and bool(owner)),
                    username=UsernameStore(
                        db,
                        self.ready
                        and bool(owner)
                        and all(
                            hasattr(self.client, method)
                            for method in (
                                "username_status",
                                "claim_username",
                            )
                        ),
                    ),
                )
            return self.libraries[owner]

    def active(self):
        with self.lock:
            return self._library(self.selected)

    def bind(self):
        with self.lock:
            g.mml_library = self._library(self.selected)
            g.mml_epoch = self.epoch

    def current(self):
        return (
            g.mml_library
            if has_request_context() and hasattr(g, "mml_library")
            else self.active()
        )

    def scope(self):
        return (
            g.mml_epoch
            if has_request_context() and hasattr(g, "mml_epoch")
            else self.epoch
        )

    def select(self, owner):
        owner = str(UUID(owner)) if owner else None
        with self.lock:
            self._library(owner)
            self.guest.execute(
                "INSERT OR REPLACE INTO settings VALUES ('cloud_active_account',?)",
                owner or "",
            )
            self.selected, self.epoch = owner, secrets.token_hex(16)
        self.wake.set()

    @staticmethod
    def checked_session(value, stored=False):
        if not isinstance(value, dict):
            raise TypeError("Invalid account session.")
        normalized = SupabaseClient.session(
            dict(value, user={"id": value.get("user_id"), "email": value.get("email")})
        )
        expiry = (
            value.get("expires_at")
            if stored
            else time.time() + normalized["expires_in"]
        )
        if type(expiry) not in (int, float) or not math.isfinite(expiry) or expiry <= 0:
            raise ValueError("Invalid account session expiry.")
        normalized["expires_at"] = expiry
        normalized["profile"] = validate_profile(
            value.get("profile", normalized["profile"])
        )
        return normalized

    def accept_session(self, value):
        value = self.checked_session(value)
        owner = str(UUID(value["user_id"]))
        with self.lock:
            self.vault.save(value)
            self.session = value
            library = self._library(owner)
            library.db.execute(
                "INSERT OR REPLACE INTO settings VALUES ('cloud_email',?)",
                value["email"],
            )
            library.profile.receive(value["profile"])
            # Signing into an account starts sync. The separate guest database
            # is adopted only through the explicit library-copy action.
            library.db.execute(
                "INSERT OR REPLACE INTO settings (key,value) "
                "SELECT 'cloud_enabled', CASE WHEN EXISTS ("
                "SELECT 1 FROM settings WHERE key='cloud_sync_paused' AND value='1'"
                ") THEN '0' ELSE '1' END",
            )
            self.states.pop(owner, None)
            self.select(owner)

    def token(self, owner):
        with self.auth_lock:
            with self.lock:
                value = self.session
                if not value or value["user_id"] != owner:
                    raise CloudError("Sign in again to resume cloud sync.", "auth")
                if value.get("expires_at", 0) >= time.time() + 60:
                    return value["access_token"]
            # Network I/O must not hold the workspace lock or block offline reads.
            fresh = self.client.refresh(value["refresh_token"])
            if fresh["user_id"] != owner:
                raise CloudError("Sign in again to resume cloud sync.", "auth")
            fresh = self.checked_session(fresh)
            with self.lock:
                if self.session is not value:
                    raise CloudError("Sign in again to resume cloud sync.", "auth")
                self.vault.save(fresh)
                self.session = fresh
                return fresh["access_token"]

    def authenticated_call(self, owner, function, *args):
        token = self.token(owner)
        try:
            return function(token, *args)
        except CloudError as error:
            if error.kind != "auth":
                raise
        with self.lock:
            if self.session and self.session["user_id"] == owner:
                self.session["expires_at"] = 0
        return function(self.token(owner), *args)

    def sign_out(self):
        with self.lock:
            value = self.session
            self.session = None
            self.select(None)
            try:
                self.vault.clear()
            except OSError:
                # The persisted selection is already guest, so an old sealed
                # session cannot be reused at startup even if deletion fails.
                self.app.logger.warning("Could not remove the sealed cloud session.")
        if value and self.client:
            try:
                self.client.sign_out(value["access_token"])
            except CloudError:
                pass  # Local logout always succeeds, including offline.

    def enabled(self, library):
        rows = library.db.query("SELECT value FROM settings WHERE key='cloud_enabled'")
        return bool(library.owner and rows and rows[0]["value"] == "1")

    def set_enabled(self, value):
        library = self.current()
        if not library.owner:
            raise ValueError("Sign in to enable cloud sync.")
        with library.db.connect(write=True) as con:
            con.executemany(
                "INSERT OR REPLACE INTO settings VALUES (?,?)",
                [
                    ("cloud_enabled", "1" if value else "0"),
                    ("cloud_sync_paused", "0" if value else "1"),
                ],
            )
        self.states.pop(library.owner, None)
        self.wake.set()

    def status(self):
        library = self.current()
        rows = library.db.query("SELECT value FROM settings WHERE key='cloud_email'")
        state = self.states.get(library.owner, {})
        profile = library.profile.snapshot()
        if not library.owner:
            profile["dirty"] = False
        if not library.owner:
            label, state_name = "Saved on this device", "local"
        elif not self.session or self.session["user_id"] != library.owner:
            label, state_name = "Sign in to resume sync", "attention"
        elif not self.enabled(library):
            label, state_name = "Sync paused", "paused"
        elif state.get("kind") == "offline":
            label, state_name = (
                "Saved on this device · waiting for connection",
                "offline",
            )
        elif state.get("kind") == "limited":
            label, state_name = "Saved on this device · sync will retry", "waiting"
        elif state.get("kind") or state.get("message", "").startswith("Sync needs"):
            label, state_name = "Sync needs attention", "attention"
        elif library.db.query("SELECT COUNT(*) n FROM sync_conflicts")[0]["n"]:
            label, state_name = "Review sync conflicts", "attention"
        elif library.store.pending() or profile["dirty"]:
            label, state_name = "Syncing…", "syncing"
        elif state.get("last_synced"):
            label, state_name = "Up to date", "current"
        else:
            label, state_name = "Syncing…", "syncing"
        username = library.username.view()
        sharing = library.sharing.view()
        sharing["visitor_path"] = (
            "/profiles/" + sharing["share_id"] if sharing["share_id"] else None
        )
        if username["username"]:
            sharing["url"] = username["url"]
            sharing["visitor_path"] = "/profiles/u/" + username["username"]
        return {
            "ready": bool(self.ready and self.client),
            "owner": library.owner,
            "email": rows[0]["value"] if rows else "",
            "enabled": self.enabled(library),
            "signed_in": bool(
                self.session and self.session["user_id"] == library.owner
            ),
            "pending": library.store.pending() + int(profile["dirty"]),
            "profile": profile["profile"],
            "sharing": sharing,
            "username": username,
            "label": label,
            "state": state_name,
            "message": state.get("message", ""),
            "last_synced": state.get("last_synced"),
            "conflicts": library.db.query("SELECT COUNT(*) n FROM sync_conflicts")[0][
                "n"
            ],
        }

    def sync_sharing(self, library, *, force=False, read_only=False):
        sharing = library.sharing
        if (
            not sharing.ready
            or not library.owner
            or not force
            and sharing.next_attempt > time.monotonic()
        ):
            return
        try:
            operation = sharing.snapshot().get("operation")
            if operation and not read_only:
                reply = self.authenticated_call(
                    library.owner, self.client.write_showcase, operation
                )
                sharing.complete(operation, reply)
            else:
                remote = self.authenticated_call(
                    library.owner, self.client.sharing_status
                )
                sharing.remote(remote)
            if not read_only and sharing.snapshot().get("operation"):
                sharing.next_attempt = 0
                self.wake.set()
            else:
                sharing.next_attempt = time.monotonic() + 60
        except CloudError as error:
            sharing.error(error.kind)
            sharing.next_attempt = time.monotonic() + max(30, error.retry_after)
        except (ValueError, TypeError, KeyError):
            sharing.error("protocol")
            sharing.next_attempt = time.monotonic() + 60

    def sync_username(self, library):
        store = library.username
        if not store.ready or store.next_attempt > time.monotonic():
            return
        try:
            value = self.authenticated_call(library.owner, self.client.username_status)
            store.receive(value)
            store.next_attempt = time.monotonic() + 300
        except CloudError as error:
            store.error(error.kind)
            store.next_attempt = time.monotonic() + max(60, error.retry_after)
        except (TypeError, ValueError, OSError):
            store.error("protocol")
            store.next_attempt = time.monotonic() + 300

    def run_once(self):
        if (
            not self.ready
            or not self.client
            or not self.run_lock.acquire(blocking=False)
        ):
            return
        try:
            library = self.active()
            owner = library.owner
            # Privacy revocation is attempted before library retries, even when
            # ordinary synchronization is paused or the library has conflicts.
            sharing_state = library.sharing.snapshot()
            sharing_operation = sharing_state.get("operation")
            if sharing_operation and sharing_operation["action"] == "unpublish":
                self.sync_sharing(library)
            elif library.sharing.ready and (
                not sharing_operation or not sharing_state.get("checked")
            ):
                # Learn the server's setting before the first local profile edit.
                # Failure here must not block ordinary private library sync.
                self.sync_sharing(library, read_only=True)
            self.sync_username(library)
            if not self.enabled(library):
                # Pausing movie sync must not freeze visibility from another device.
                # Pending publications remain frozen until sync is resumed.
                if sharing_operation and sharing_operation["action"] != "unpublish":
                    self.sync_sharing(library, read_only=True)
                return
            state = self.states.setdefault(owner, {})
            if state.get("retry_at", 0) > time.monotonic():
                return
            try:
                if not state.get("healthy"):
                    self.client.health()
                    state["healthy"] = True
                profile = library.profile.snapshot()
                if profile["dirty"]:
                    self.authenticated_call(
                        owner, self.client.update_profile, profile["profile"]
                    )
                    if self.selected != owner:
                        return
                    library.profile.receive(profile["profile"], profile["generation"])
                    if library.sharing.ready:
                        library.sharing.queue("update", profile["profile"])
                    state["profile_checked"] = time.monotonic()
                elif time.monotonic() - state.get("profile_checked", -300) >= 300:
                    remote = self.authenticated_call(owner, self.client.profile)
                    if self.selected != owner:
                        return
                    if remote["user_id"] != owner:
                        raise ValueError("Invalid profile owner.")
                    library.profile.receive(remote["profile"])
                    state["profile_checked"] = time.monotonic()
                for _ in range(20):
                    if self.selected != owner or not self.enabled(library):
                        return
                    operation = library.store.next_operation()
                    if operation is None:
                        break
                    reply = self.authenticated_call(owner, self.client.push, operation)
                    if reply.get("record_key") != operation["record_key"]:
                        raise ValueError("Invalid sync record identity.")
                    if reply.get("status") == "applied":
                        library.store.acknowledge(operation, reply["revision"])
                    elif reply.get("status") == "conflict" and isinstance(
                        reply.get("remote"), dict
                    ):
                        library.store.reject_conflict(operation, reply["remote"])
                    else:
                        raise ValueError("Invalid synchronization acknowledgement.")
                # Frozen uploads always finish before downloads. Concurrent local
                # edits remain dirty and are merged against the downloaded baseline.
                if library.db.query("SELECT COUNT(*) n FROM sync_outbox")[0]["n"]:
                    self.wake.set()
                    return
                for _ in range(10):
                    if self.selected != owner or not self.enabled(library):
                        return
                    page = self.authenticated_call(
                        owner, self.client.pull, library.store.cursor()
                    )
                    library.store.apply_page(page)
                    if len(page["changes"]) < 25:
                        break
                state.update(
                    message="Cloud sync is up to date.",
                    last_synced=time.time(),
                    failures=0,
                    retry_at=0,
                    kind="",
                )
                self.sync_sharing(library)
                if (
                    library.store.pending()
                    > library.db.query("SELECT COUNT(*) n FROM sync_conflicts")[0]["n"]
                ):
                    self.wake.set()
            except CloudError as error:
                failures = state.get("failures", 0) + 1
                state.update(
                    message=str(error),
                    kind=error.kind,
                    failures=failures,
                    retry_at=time.monotonic()
                    + min(1800, max(error.retry_after, 30 * 2 ** min(failures - 1, 5))),
                )
                if error.kind == "setup":
                    state["healthy"] = False
                if error.kind == "auth":
                    with self.lock:
                        if self.session and self.session.get("user_id") == owner:
                            self.session = None
                            try:
                                self.vault.clear()
                            except OSError:
                                self.app.logger.warning(
                                    "Could not remove the expired sealed cloud session."
                                )
            except (ValueError, KeyError, TypeError):
                state.update(
                    message="Sync needs attention. Your local changes are preserved.",
                    retry_at=time.monotonic() + 300,
                )
            except (OSError, sqlite3.Error):
                state.update(
                    message="Sync needs attention. Your local changes are preserved.",
                    retry_at=time.monotonic() + 300,
                )
        finally:
            self.run_lock.release()

    def _work(self):
        while not self.stopped.is_set():
            try:
                self.run_once()
            except (OSError, sqlite3.Error):
                # A local library temporarily unavailable during startup must not
                # kill the worker or cause an unbounded retry loop.
                self.states.setdefault(self.selected, {}).update(
                    message="Sync needs attention. Your local changes are preserved.",
                    retry_at=time.monotonic() + 300,
                )
            # Clear before work so a wake issued during a sync is not lost.
            # Successful local writes wake this worker through after_request.
            if self.wake.wait(30):
                self.wake.clear()
                self.stopped.wait(0.75)

    def close(self):
        self.stopped.set()
        self.wake.set()
        if self.thread:
            self.thread.join(timeout=2)
        for library in list(self.libraries.values()):
            library.catalog.close()
