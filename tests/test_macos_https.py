"""Mac-only HTTPS bootstrap and read-only packaged diagnostics."""

import importlib.util
import json
import runpy
import ssl
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

HOOK = Path(__file__).resolve().parents[1] / "scripts/pyi_rth_macos_https.py"


@pytest.fixture
def bootstrap(monkeypatch):
    # The package is required for Mac builds; other source runners may omit it.
    certifi = pytest.importorskip("certifi")
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.setattr(sys, "argv", ["MyMovieList"])
    spec = importlib.util.spec_from_file_location("mac_https_bootstrap", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, certifi


def test_bootstrap_loads_real_ca_bundle_and_keeps_peer_verification(bootstrap):
    _module, certifi = bootstrap
    assert ssl.get_default_verify_paths().cafile == certifi.where()
    context = ssl.create_default_context()
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    assert context.cert_store_stats()["x509_ca"] > 100


def test_explicit_custom_trust_store_is_preserved(bootstrap, tmp_path, monkeypatch):
    module, certifi = bootstrap
    custom = tmp_path / "organization.pem"
    custom.write_bytes(Path(certifi.where()).read_bytes())
    monkeypatch.setenv("SSL_CERT_FILE", str(custom))
    module.configure_certificates()
    assert ssl.get_default_verify_paths().cafile == str(custom)
    assert ssl.create_default_context().verify_mode == ssl.CERT_REQUIRED


def test_missing_packaged_trust_store_fails_closed(bootstrap, tmp_path, monkeypatch):
    module, certifi = bootstrap
    monkeypatch.setattr(certifi, "where", lambda: str(tmp_path / "missing.pem"))
    with pytest.raises(RuntimeError, match="certificate bundle is missing"):
        module.configure_certificates()


@pytest.fixture
def probes(bootstrap, tmp_path, monkeypatch):
    import cloud_client
    import tmdb_client

    module, _certifi = bootstrap
    config = tmp_path / "supabase/project.json"
    config.parent.mkdir()
    config.write_text(
        json.dumps(
            {
                "url": "https://test.supabase.co",
                "publishable_key": "sb_publishable_test",
            }
        )
    )
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    calls = []

    class MovieClient:
        response = {"id": 603}

        def get(self, path):
            calls.append(("movie", path))
            return self.response

    class CloudClient:
        response = {"disable_signup": False}
        error = None

        def __init__(self, url, key):
            assert url == "https://test.supabase.co" and key == "sb_publishable_test"

        def request(self, path, *, method):
            calls.append(("cloud", path, method))
            if self.error:
                raise self.error
            return self.response

    monkeypatch.setattr(tmdb_client, "TMDBClient", MovieClient)
    monkeypatch.setattr(cloud_client, "SupabaseClient", CloudClient)
    return module, calls, MovieClient, CloudClient


def test_online_probe_uses_only_public_read_requests(probes, capsys):
    module, calls, _movie, _cloud = probes
    assert module.https_self_test() == 0
    assert calls == [("movie", "movie/603"), ("cloud", "/auth/v1/settings", "GET")]
    result = json.loads(capsys.readouterr().out)
    assert result["result"] == "passed" and result["read_only"]
    assert result["certificate_verification"] and result["cloud_auth_https"]


def test_online_probe_rejects_disabled_certificate_checks(probes, monkeypatch, capsys):
    module, calls, _movie, _cloud = probes
    monkeypatch.setattr(
        module.ssl,
        "create_default_context",
        lambda: SimpleNamespace(check_hostname=False),
    )
    assert module.https_self_test() == 1
    assert calls == []
    assert json.loads(capsys.readouterr().out)["check"] == "certificates"


def test_online_probe_redacts_provider_failure_data(probes, capsys):
    from cloud_client import CloudError

    module, _calls, _movie, cloud = probes
    cloud.error = CloudError("PRIVATE-SESSION-TOKEN private@example.invalid")
    assert module.https_self_test() == 1
    output = capsys.readouterr().out
    assert "PRIVATE-SESSION-TOKEN" not in output and "private@example" not in output
    assert json.loads(output)["check"] == "cloud_auth"


@pytest.mark.parametrize("service", ["movie", "cloud"])
def test_online_probe_rejects_wrong_service_responses(probes, capsys, service):
    module, _calls, movie, cloud = probes
    if service == "movie":
        movie.response = {"id": 999}
    else:
        cloud.response = {"disable_signup": "false"}
    assert module.https_self_test() == 1
    assert json.loads(capsys.readouterr().out)["result"] == "failed"


def test_diagnostic_flag_exits_before_application_start(probes, monkeypatch, capsys):
    _module, calls, _movie, _cloud = probes
    monkeypatch.setattr(sys, "argv", ["MyMovieList", "--https-self-test"])
    with pytest.raises(SystemExit) as exit_code:
        runpy.run_path(str(HOOK))
    assert exit_code.value.code == 0
    assert json.loads(capsys.readouterr().out)["result"] == "passed"
    assert calls == [("movie", "movie/603"), ("cloud", "/auth/v1/settings", "GET")]
