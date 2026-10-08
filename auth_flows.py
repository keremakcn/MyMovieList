"""Bounded, short-lived auth steps. Browser cookies contain only opaque IDs."""

import secrets
import threading
import time
from contextlib import contextmanager


class AuthFlows:
    def __init__(self, clock=time.monotonic, capacity=128):
        self.clock, self.capacity = clock, capacity
        self.lock = threading.RLock()
        self.steps = {}

    def start(self, purpose, email, scope):
        with self.lock:
            self._prune()
            if len(self.steps) >= self.capacity:
                raise ValueError("Too many account requests. Please try again shortly.")
            key = secrets.token_urlsafe(32)
            self.steps[key] = {
                "purpose": purpose,
                "email": email,
                "scope": scope,
                "stage": "code",
                "sent_at": self.clock(),
                "expires": self.clock() + 1800,
                "lock": threading.RLock(),
            }
            return key

    def _prune(self):
        for key, step in list(self.steps.items()):
            if step["expires"] <= self.clock():
                self.steps.pop(key, None)

    def view(self, key, scope):
        with self.lock:
            self._prune()
            step = self.steps.get(key)
            if not step or step["scope"] != scope:
                return None
            return {
                k: step[k]
                for k in ("purpose", "email", "stage", "sent_at", "username")
                if k in step
            }

    @contextmanager
    def use(self, key, scope, purpose, stage):
        with self.lock:
            self._prune()
            step = self.steps.get(key)
        if step is None:
            raise ValueError("This verification has expired. Request a new code.")
        with step["lock"]:
            with self.lock:
                if (
                    self.steps.get(key) is not step
                    or step["scope"] != scope
                    or step["purpose"] != purpose
                    or step["stage"] != stage
                    or step["expires"] <= self.clock()
                ):
                    raise ValueError(
                        "This verification has expired. Request a new code."
                    )
            yield step

    def verified(self, step, credentials, stage="password"):
        step.update(
            stage=stage,
            credentials=credentials,
            expires=self.clock() + min(600, credentials["expires_in"]),
        )

    def discard(self, key):
        with self.lock:
            self.steps.pop(key, None)
