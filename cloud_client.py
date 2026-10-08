"""Small Supabase adapter; only a publishable key ships with the application."""

import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID

from account_profile import remote_profile, validate_profile
from account_username import normalize_username, validate_username_status
from profile_sharing import validate_public_profile, validate_settings
from social import normalize_query, validate_page, validate_position


class CloudError(Exception):
    def __init__(self, message, kind="offline", retry_after=30):
        super().__init__(message)
        self.kind, self.retry_after = kind, retry_after


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # An authorization header must never follow an upstream redirect.
        return None


class SupabaseClient:
    def __init__(self, url, key, opener=None):
        if not isinstance(url, str) or not isinstance(key, str):
            raise TypeError("Choose a valid Supabase URL and publishable key.")
        parts = urlsplit(url)
        if (
            parts.scheme != "https"
            or not re.fullmatch(r"[a-z0-9-]+\.supabase\.co", parts.netloc)
            or parts.path not in ("", "/")
            or parts.query
            or parts.fragment
        ):
            raise ValueError("Choose a valid Supabase Project URL.")
        if not re.fullmatch(r"sb_publishable_[A-Za-z0-9_-]+", key):
            raise ValueError("Use a Supabase publishable key.")
        self.url, self.key = url.rstrip("/"), key
        self.opener = opener or build_opener(NoRedirect())

    def request(self, path, body=None, *, token=None, method="POST"):
        headers = {
            "apikey": self.key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if token:
            headers["Authorization"] = "Bearer " + token
        request = Request(
            self.url + path,
            data=json.dumps(body).encode("utf-8") if body is not None else None,
            method=method,
            headers=headers,
        )
        try:
            with self.opener.open(request, timeout=12) as response:
                raw = response.read(5 * 1024 * 1024 + 1)
                if len(raw) > 5 * 1024 * 1024:
                    raise CloudError(
                        "Cloud returned an unexpected response.", "protocol"
                    )
                payload = json.loads(raw) if raw else {}
                if not isinstance(payload, dict):
                    raise CloudError(
                        "Cloud returned an unexpected response.", "protocol"
                    )
                return payload
        except HTTPError as error:
            try:
                payload = json.loads(error.read(8192))
                code = (
                    (payload.get("code") or payload.get("error_code"))
                    if isinstance(payload, dict)
                    else None
                )
            except (ValueError, UnicodeError):
                code = None
            # Never display raw provider errors: they can contain submitted data.
            if code == "22023" and path == "/rest/v1/rpc/mml_claim_username":
                raise CloudError(
                    "This name is not allowed. Choose another one.", "validation"
                ) from None
            if code in ("email_not_confirmed",):
                raise CloudError(
                    "Confirm your email before signing in.", "auth"
                ) from None
            if code in ("email_address_not_authorized", "over_email_send_rate_limit"):
                raise CloudError(
                    "Email delivery is unavailable. Please try again later.", "email"
                ) from None
            if code in ("otp_expired",):
                raise CloudError(
                    "The confirmation code is invalid or expired.", "auth"
                ) from None
            if (
                code in ("invalid_credentials", "weak_password", "user_already_exists")
                or error.code == 400
                and path.startswith("/auth/")
            ):
                raise CloudError(
                    "Check your email, password or confirmation code and try again.",
                    "auth",
                ) from None
            if error.code == 429 or error.code == 402:
                try:
                    wait = min(
                        1800, max(30, int(error.headers.get("Retry-After", "60")))
                    )
                except (ValueError, TypeError):
                    wait = 60
                raise CloudError(
                    "Cloud is temporarily limited. Your changes are saved on this device.",
                    "limited",
                    wait,
                ) from None
            if error.code == 401:
                raise CloudError(
                    "Sign in again to resume cloud sync.", "auth"
                ) from None
            if error.code in (403, 404) or code == "PGRST202":
                raise CloudError(
                    "Cloud setup is not ready. Your local library is available.",
                    "setup",
                    300,
                ) from None
            raise CloudError(
                "Cloud is unavailable. Your changes are saved on this device.",
                "offline",
                60,
            ) from None
        except (URLError, OSError, TimeoutError):
            raise CloudError(
                "Could not reach the cloud. Your changes are saved on this device."
            ) from None
        except (ValueError, UnicodeError):
            raise CloudError(
                "Cloud returned an unexpected response.", "protocol"
            ) from None

    @staticmethod
    def session(response):
        try:
            user = response["user"]
            owner = str(UUID(user["id"]))
            access, refresh = response["access_token"], response["refresh_token"]
            expires = response.get("expires_in", 3600)
            if (
                not isinstance(access, str)
                or not access
                or not isinstance(refresh, str)
                or not refresh
                or type(expires) is not int
                or not 1 <= expires <= 86400
            ):
                raise ValueError
            if not isinstance(user.get("email"), str) or len(user["email"]) > 320:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise CloudError(
                "Cloud returned an unexpected account response.", "protocol"
            ) from None
        return {
            "user_id": owner,
            "email": user["email"],
            "access_token": access,
            "refresh_token": refresh,
            "expires_in": expires,
            "profile": remote_profile(user.get("user_metadata")),
            "registration_pending": (
                isinstance(user.get("user_metadata"), dict)
                and user["user_metadata"].get("mml_registration") == "pending-v1"
            ),
        }

    def sign_in(self, email, password):
        return self.session(
            self.request(
                "/auth/v1/token?grant_type=password",
                {"email": email, "password": password},
            )
        )

    def sign_up(self, email, password):
        response = self.request(
            "/auth/v1/signup", {"email": email, "password": password}
        )
        return self.session(response) if response.get("access_token") else None

    def begin_signup(self, email):
        # Supabase applies this metadata to newly created/unconfirmed accounts.
        # Confirmed existing accounts keep their password and existing metadata.
        self.request(
            "/auth/v1/otp",
            {
                "email": email,
                "create_user": True,
                "data": {"mml_registration": "pending-v1"},
            },
        )

    def complete_signup(self, token, password):
        self.request(
            "/auth/v1/user",
            {
                "password": password,
                "data": {"mml_registration": "complete-v1"},
            },
            token=token,
            method="PUT",
        )

    def profile(self, token):
        value = self.request("/auth/v1/user", token=token, method="GET")
        try:
            owner = str(UUID(value["id"]))
        except (KeyError, TypeError, ValueError):
            raise CloudError(
                "Cloud returned an unexpected account response.", "protocol"
            ) from None
        return {"user_id": owner, "profile": remote_profile(value.get("user_metadata"))}

    def update_profile(self, token, profile):
        self.request(
            "/auth/v1/user",
            {"data": {"mml_profile": validate_profile(profile)}},
            token=token,
            method="PUT",
        )

    def sharing_status(self, token):
        return validate_settings(
            self.request("/rest/v1/rpc/mml_sharing_status", {}, token=token)
        )

    def write_showcase(self, token, operation):
        return self.request(
            "/rest/v1/rpc/mml_write_showcase",
            {
                "p_operation_id": operation["operation_id"],
                "p_expected_revision": operation["expected_revision"],
                "p_action": operation["action"],
                "p_payload": operation["payload"],
            },
            token=token,
        )

    def public_profile(self, share_id):
        # Public reads never send the current owner's session credentials.
        return validate_public_profile(
            self.request(
                "/rest/v1/rpc/mml_public_profile", {"p_share_id": str(UUID(share_id))}
            )
        )

    def username_status(self, token):
        return validate_username_status(
            self.request("/rest/v1/rpc/mml_username_status", {}, token=token)
        )

    def claim_username(self, token, username):
        username = normalize_username(username, writing=True)
        value = self.request(
            "/rest/v1/rpc/mml_claim_username", {"p_username": username}, token=token
        )
        if (
            not isinstance(value, dict)
            or set(value) != {"status", "username"}
            or value["status"] not in ("claimed", "taken", "locked")
        ):
            raise ValueError("Invalid username response.")
        validate_username_status({"username": value["username"]})
        if (
            (value["status"] == "claimed" and value["username"] != username)
            or (value["status"] == "taken" and value["username"] is not None)
            or (
                value["status"] == "locked"
                and (not value["username"] or value["username"] == username)
            )
        ):
            raise ValueError("Invalid username response.")
        return value

    def username_health(self):
        value = self.request("/rest/v1/rpc/mml_username_protocol", {})
        if value != {"service": "mymovielist-usernames", "protocol": 2}:
            raise CloudError(
                "Usernames are being prepared. Please try again later.", "setup"
            )

    def public_profile_by_username(self, username):
        username = normalize_username(username)
        value = validate_public_profile(
            self.request(
                "/rest/v1/rpc/mml_public_profile_by_username", {"p_username": username}
            )
        )
        if value["found"] and value.get("username") != username:
            raise ValueError("Invalid public profile.")
        return value

    def social_page(self, view="people", query="", cursor=None):
        if view not in ("people", "week"):
            raise ValueError("Choose a valid social view.")
        query = normalize_query(query)
        cursor = validate_position(view, cursor)
        return validate_page(
            self.request(
                "/rest/v1/rpc/mml_social_page",
                {
                    "p_view": view,
                    "p_query": query,
                    "p_cursor": cursor,
                },
            ),
            view,
        )

    def verify(self, email, code, kind="email"):
        if kind not in ("email", "recovery") or not re.fullmatch(r"[0-9]{6,10}", code):
            raise CloudError("The confirmation code is invalid or expired.", "auth")
        return self.session(
            self.request(
                "/auth/v1/verify", {"email": email, "token": code, "type": kind}
            )
        )

    def refresh(self, refresh_token):
        return self.session(
            self.request(
                "/auth/v1/token?grant_type=refresh_token",
                {"refresh_token": refresh_token},
            )
        )

    def recover(self, email):
        self.request("/auth/v1/recover", {"email": email})

    def change_password(self, token, password):
        self.request("/auth/v1/user", {"password": password}, token=token, method="PUT")

    def sign_out(self, token):
        self.request("/auth/v1/logout?scope=local", token=token)

    def health(self):
        response = self.request("/rest/v1/rpc/mml_cloud_status", {})
        if (
            response.get("service") != "mymovielist-sync"
            or type(response.get("protocol")) is not int
            or response.get("protocol") != 1
        ):
            raise CloudError(
                "Cloud setup is not ready. Your local library is available.", "setup"
            )

    def push(self, token, operation):
        return self.request(
            "/rest/v1/rpc/mml_push_change",
            {
                "p_operation_id": operation["operation_id"],
                "p_record_key": operation["record_key"],
                "p_expected_revision": operation["expected_revision"],
                "p_data": json.loads(operation["data_json"]),
            },
            token=token,
        )

    def pull(self, token, cursor):
        return self.request(
            "/rest/v1/rpc/mml_pull_changes",
            {"p_cursor": cursor, "p_limit": 25},
            token=token,
        )
