"""Verify source, native architecture, signatures and isolated startup of a Mac package."""

import argparse
import hashlib
import json
import marshal
import os
import plistlib
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from types import CodeType

ROOT = Path(__file__).resolve().parents[1]
MODULES = (
    "app",
    "catalog",
    "discovery",
    "discovery_routes",
    "i18n",
    "storage",
    "recommendations",
    "recommendation_model",
    "recommendation_routes",
    "tmdb_client",
    "version",
    "auth_flows",
    "account_profile",
    "account_username",
    "name_policy",
    "profile_sharing",
    "public_profile_routes",
    "cloud_client",
    "cloud_sync",
    "account_routes",
    "personal_data",
    "sync_store",
    "session_store",
    "desktop_smoke",
    "social",
    "social_routes",
    "public_catalog",
)
FORBIDDEN = {
    ".git",
    ".qa",
    ".env",
    "movies.db",
    "keystore.properties",
    "local.properties",
    "cloud-session.sealed",
    ".android-signing",
    "accounts",
    "tests",
}
MACHO = {
    b"\xfe\xed\xfa\xce",
    b"\xce\xfa\xed\xfe",
    b"\xfe\xed\xfa\xcf",
    b"\xcf\xfa\xed\xfe",
    b"\xca\xfe\xba\xbe",
    b"\xbe\xba\xfe\xca",
    b"\xca\xfe\xba\xbf",
    b"\xbf\xba\xfe\xca",
}


def run(*args, timeout=120, env=None):
    try:
        result = subprocess.run(
            [str(arg) for arg in args],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except subprocess.CalledProcessError as error:
        # Native QA uses synthetic credentials only. Keep failure diagnostics
        # visible in Actions instead of hiding Cocoa/Keychain startup errors.
        if error.stdout:
            print(error.stdout, file=sys.stderr)
        if error.stderr:
            print(error.stderr, file=sys.stderr)
        raise
    return result.stdout


def normalize(code):
    return code.replace(
        co_filename="<source>",
        co_consts=tuple(
            normalize(value) if isinstance(value, CodeType) else value
            for value in code.co_consts
        ),
    )


def verify_app(app, arch):
    import certifi
    from PyInstaller.archive.readers import CArchiveReader

    app = app.resolve()
    assert app.is_dir() and app.suffix == ".app"
    info = plistlib.loads((app / "Contents/Info.plist").read_bytes())
    version = re.search(
        r'^APP_VERSION = "([^"]+)"$',
        (ROOT / "version.py").read_text(encoding="utf-8"),
        re.MULTILINE,
    )[1]
    assert info["CFBundleIdentifier"] == "cloud.myshelf.mymovielist"
    assert info["CFBundleShortVersionString"] == info["CFBundleVersion"] == version
    assert info["LSMinimumSystemVersion"] == "15.0"
    executable = app / "Contents/MacOS" / info["CFBundleExecutable"]
    assert (app / "Contents/Resources" / info["CFBundleIconFile"]).read_bytes()[
        :4
    ] == b"icns"
    run("codesign", "--verify", "--deep", "--strict", app)
    archive = CArchiveReader(str(executable))
    pyz = archive.open_embedded_archive(
        next(name for name in archive.toc if name.endswith(".pyz"))
    )
    for name in MODULES:
        assert name in pyz.toc, name
        assert normalize(pyz.extract(name)) == normalize(
            compile(
                (ROOT / (name + ".py")).read_bytes(), "<source>", "exec", optimize=0
            )
        ), name
    assert "keyring.backends.macOS" in pyz.toc and "webview.platforms.cocoa" in pyz.toc
    assert "certifi" in pyz.toc
    https_hook = marshal.loads(archive.extract("pyi_rth_macos_https"))
    assert normalize(https_hook) == normalize(
        compile(
            (ROOT / "scripts/pyi_rth_macos_https.py").read_bytes(),
            "<source>",
            "exec",
            optimize=0,
        )
    )
    script = marshal.loads(archive.extract("run_desktop"))
    assert normalize(script) == normalize(
        compile((ROOT / "run_desktop.py").read_bytes(), "<source>", "exec", optimize=0)
    )
    resources = app / "Contents/Resources"
    certificates = resources / "certifi/cacert.pem"
    assert certificates.resolve().is_relative_to(app) and certificates.is_file()
    assert certificates.read_bytes() == Path(certifi.where()).read_bytes()
    assets = [
        p
        for folder in ("static", "templates")
        for p in (ROOT / folder).rglob("*")
        if p.is_file()
    ]
    for source in assets + [ROOT / "supabase/project.json"]:
        packaged = resources / source.relative_to(ROOT)
        assert packaged.resolve().is_relative_to(app), str(packaged)
        assert packaged.read_bytes() == source.read_bytes(), str(
            source.relative_to(ROOT)
        )
    config = json.loads(
        (resources / "supabase/project.json").read_text(encoding="utf-8")
    )
    assert (
        config["publishable_key"].startswith("sb_publishable_")
        and config["accounts_enabled"] is True
    )
    native = 0
    for path in app.rglob("*"):
        parts = path.relative_to(app).parts
        assert not set(parts) & FORBIDDEN, str(path)
        assert not path.name.startswith((".env", ".dev.vars")), str(path)
        assert path.suffix.lower() not in (
            ".jks",
            ".keystore",
            ".db",
            ".sealed",
            ".p12",
            ".pfx",
            ".mobileprovision",
            ".provisionprofile",
        ), str(path)
        if path.is_symlink():
            assert path.resolve().is_relative_to(app) and path.exists(), str(path)
        elif path.is_file():
            with path.open("rb") as file:
                header = file.read(4)
            if header in MACHO:
                assert run("lipo", "-archs", path).strip().split() == [arch], str(path)
                native += 1
    assert native > 0
    # Finder-launched apps must work without Python/CA settings from the runner.
    network_env = dict(os.environ)
    for variable in ("SSL_CERT_FILE", "SSL_CERT_DIR", "PYTHONPATH", "PYTHONHOME"):
        network_env.pop(variable, None)
    network_output = run(executable, "--https-self-test", env=network_env, timeout=60)
    network_results = [
        json.loads(line)
        for line in network_output.splitlines()
        if line.startswith('{"result":')
    ]
    assert len(network_results) == 1 and network_results[0]["result"] == "passed", (
        network_output
    )
    # The native test rejects nonempty folders before creating an app or touching Keychain.
    with tempfile.TemporaryDirectory(prefix="mymovielist-mac-qa-") as temporary:
        env = dict(os.environ, MOVIE_WATCHLIST_DATA_DIR=temporary)
        output = run(executable, "--smoke-test", env=env, timeout=120)
        results = [
            json.loads(line)
            for line in output.splitlines()
            if line.startswith('{"result":')
        ]
        assert len(results) == 1 and results[0]["result"] == "passed", output
    return {
        "result": "passed",
        "version": version,
        "architecture": arch,
        "min_macos": "15.0",
        "compiled_modules_match_source": len(MODULES),
        "ui_assets": len(assets),
        "native_binaries": native,
        "ad_hoc_signature_verified": True,
        "apple_notarized": False,
        "private_files_excluded": True,
        "smoke": results[0],
        "https": network_results[0],
        "ca_bundle_matched": True,
        "graphical_window_tested": False,
    }


def verify_dmg(dmg, arch):
    with tempfile.TemporaryDirectory(prefix="mymovielist-dmg-qa-") as mount:
        run(
            "hdiutil",
            "attach",
            "-readonly",
            "-nobrowse",
            "-mountpoint",
            mount,
            "-plist",
            dmg,
        )
        try:
            path = Path(mount)
            assert {p.name for p in path.iterdir() if not p.name.startswith(".")} == {
                "MyMovieList.app",
                "Applications",
                "READ ME.txt",
            }
            assert (path / "Applications").is_symlink() and os.readlink(
                path / "Applications"
            ) == "/Applications"
            result = verify_app(path / "MyMovieList.app", arch)
        finally:
            run("hdiutil", "detach", mount)
    result.update(
        package=str(dmg),
        sha256=hashlib.sha256(dmg.read_bytes()).hexdigest(),
        delivered_dmg_verified=True,
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    files = parser.add_mutually_exclusive_group(required=True)
    files.add_argument("--app", type=Path)
    files.add_argument("--dmg", type=Path)
    parser.add_argument("--arch", choices=("arm64", "x86_64"), required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("Native Mac package verification requires macOS.")
    report = (
        verify_app(args.app, args.arch) if args.app else verify_dmg(args.dmg, args.arch)
    )
    if args.report:
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report), flush=True)
