"""Give the Mac bundle its own verified HTTPS trust store before app imports."""

import json
import os
import ssl
import sys
from pathlib import Path

import certifi


def configure_certificates():
    bundle = Path(certifi.where())
    if not bundle.is_file():
        raise RuntimeError("The application's HTTPS certificate bundle is missing.")
    # A deliberately configured corporate trust store remains supported.
    os.environ.setdefault("SSL_CERT_FILE", str(bundle))


def https_self_test():
    """Read-only live checks; no library, Keychain or user account is touched."""
    check = "certificates"
    try:
        context = ssl.create_default_context()
        if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
            raise RuntimeError("HTTPS certificate verification must stay enabled.")
        if not context.cert_store_stats()["x509_ca"]:
            raise RuntimeError("The packaged HTTPS trust store is empty.")

        from tmdb_client import TMDBClient

        check = "movie_discovery"
        movie = TMDBClient().get("movie/603")
        if movie.get("id") != 603:
            raise ValueError("Unexpected discovery response.")

        from cloud_client import SupabaseClient

        check = "cloud_auth"
        config = json.loads(
            (Path(sys._MEIPASS) / "supabase/project.json").read_text(encoding="utf-8")
        )
        settings = SupabaseClient(config["url"], config["publishable_key"]).request(
            "/auth/v1/settings", method="GET"
        )
        if type(settings.get("disable_signup")) is not bool:
            raise ValueError("Unexpected cloud authentication response.")
        result = {
            "result": "passed",
            "hostname_verification": True,
            "certificate_verification": True,
            "movie_discovery_https": True,
            "cloud_auth_https": True,
            "read_only": True,
        }
        status = 0
    except Exception as error:
        # Never print headers, provider bodies, credentials or personal data.
        cause = error.__cause__
        result = {
            "result": "failed",
            "check": check,
            "error_type": type(error).__name__,
            "cause_type": type(cause).__name__ if cause else None,
        }
        status = 1
    print(json.dumps(result), flush=True)
    return status


configure_certificates()
if "--https-self-test" in sys.argv:
    raise SystemExit(https_self_test())
