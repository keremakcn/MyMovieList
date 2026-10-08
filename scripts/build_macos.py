"""Build an ad-hoc signed Mac beta DMG on a native macOS runner."""

import argparse
import hashlib
import json
import os
import platform
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args, capture=False):
    result = subprocess.run(
        [str(arg) for arg in args],
        check=True,
        cwd=ROOT,
        text=True,
        capture_output=capture,
    )
    return result.stdout if capture else None


def build(arch):
    if sys.platform != "darwin":
        raise RuntimeError(
            "Mac packages must be built on macOS, locally or in GitHub Actions."
        )
    host = {"aarch64": "arm64", "AMD64": "x86_64"}.get(
        platform.machine(), platform.machine()
    )
    if host != arch:
        raise RuntimeError(f"Use a native {arch} runner; the current Python is {host}.")
    version = re.search(
        r'^APP_VERSION = "([^"]+)"$',
        (ROOT / "version.py").read_text(encoding="utf-8"),
        re.MULTILINE,
    )[1]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise RuntimeError("Invalid shared release version.")
    for tool in ("sips", "iconutil", "codesign", "hdiutil", "ditto", "lipo"):
        if not shutil.which(tool):
            raise RuntimeError(f"Required macOS tool is missing: {tool}")
    # Every mutable build file stays in an architecture-specific workspace.
    requested = ROOT / "build/macos" / arch
    work = requested.resolve()
    if work != requested or not work.is_relative_to(ROOT / "build"):
        raise RuntimeError(
            "The Mac build directory must not be redirected by symlinks."
        )
    work.mkdir(parents=True, exist_ok=True)
    icons = work / "MyMovieList.iconset"
    icons.mkdir(exist_ok=True)
    source_icon = ROOT / "static/branding/mymovielist-logo.png"
    for size in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            destination = icons / f"icon_{size}x{size}{'@2x' if scale == 2 else ''}.png"
            run(
                "sips",
                "-z",
                size * scale,
                size * scale,
                source_icon,
                "--out",
                destination,
                capture=True,
            )
    icon = work / "MyMovieList.icns"
    run("iconutil", "-c", "icns", icons, "-o", icon)
    os.environ["MACOSX_DEPLOYMENT_TARGET"] = "15.0"
    run(
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",
        "--name",
        "MyMovieList",
        "--icon",
        icon,
        "--target-arch",
        arch,
        "--osx-bundle-identifier",
        "cloud.myshelf.mymovielist",
        "--hidden-import",
        "keyring.backends.macOS",
        "--hidden-import",
        "webview.platforms.cocoa",
        "--exclude-module",
        "PyQt5",
        "--exclude-module",
        "PyQt6",
        "--exclude-module",
        "PySide2",
        "--exclude-module",
        "PySide6",
        "--copy-metadata",
        "keyring",
        "--collect-submodules",
        "keyring.backends.macOS",
        "--collect-data",
        "certifi",
        "--runtime-hook",
        ROOT / "scripts/pyi_rth_macos_https.py",
        # PyInstaller resolves data sources relative to --specpath.
        # Keep sources rooted in the project and destinations inside the bundle.
        "--add-data",
        f"{ROOT / 'templates'}:templates",
        "--add-data",
        f"{ROOT / 'static'}:static",
        "--add-data",
        f"{ROOT / 'supabase/project.json'}:supabase",
        "--codesign-identity",
        "-",
        "--distpath",
        work / "dist",
        "--workpath",
        work / "pyinstaller",
        "--specpath",
        work,
        ROOT / "run_desktop.py",
    )
    app = work / "dist/MyMovieList.app"
    plist = app / "Contents/Info.plist"
    data = plistlib.loads(plist.read_bytes())
    data.update(
        CFBundleShortVersionString=version,
        CFBundleVersion=version,
        LSMinimumSystemVersion="15.0",
        NSHighResolutionCapable=True,
    )
    plist.write_bytes(plistlib.dumps(data))
    # PyInstaller has already signed nested binaries. Re-sign the outer bundle
    # after its version metadata changes, then verify every nested signature.
    run("codesign", "--force", "--sign", "-", app)
    run("codesign", "--verify", "--deep", "--strict", app)
    run(sys.executable, ROOT / "scripts/verify_macos.py", "--app", app, "--arch", arch)
    output = ROOT / "dist/macos" / f"v{version}"
    output.mkdir(parents=True, exist_ok=True)
    name = f"MyMovieList-v{version}-macos-{arch}-beta"
    dmg = output / (name + ".dmg")
    with tempfile.TemporaryDirectory(prefix="dmg-", dir=work) as temporary:
        image_root = Path(temporary)
        # ditto preserves the app bundle's symlinks, signatures and metadata.
        run("ditto", app, image_root / "MyMovieList.app")
        (image_root / "Applications").symlink_to(
            "/Applications", target_is_directory=True
        )
        instructions = (
            f"MyMovieList v{version} — macOS beta ({arch})\n\n"
            "Requires macOS 15 or later. Drag MyMovieList.app to Applications.\n"
            "This beta uses an ad-hoc signature and has not been notarized by Apple.\n"
            "After attempting to open it, use System Settings > Privacy & Security > Open Anyway if offered.\n"
            "https://support.apple.com/en-us/102445\n\n"
            "Your library stays in ~/Library/Application Support/MyMovieList.\n"
            "Replace the application to update; keep its data directory.\n\n"
            "macOS beta. Uygulamayı Applications klasörüne sürükle.\n"
            "İlk açılışta uyarı çıkarsa Sistem Ayarları > Gizlilik ve Güvenlik > Yine de Aç seçeneğini kullan.\n"
        )
        (image_root / "READ ME.txt").write_text(instructions, encoding="utf-8")
        run(
            "hdiutil",
            "create",
            "-ov",
            "-format",
            "UDZO",
            "-volname",
            f"MyMovieList {version}",
            "-srcfolder",
            image_root,
            dmg,
        )
    run("hdiutil", "verify", dmg)
    checksum = hashlib.sha256(dmg.read_bytes()).hexdigest()
    (output / (name + "-SHA256SUMS.txt")).write_text(
        f"{checksum}  {dmg.name}\n", encoding="ascii"
    )
    # Inspect the delivered image as well as the original bundle.
    run(
        sys.executable,
        ROOT / "scripts/verify_macos.py",
        "--dmg",
        dmg,
        "--arch",
        arch,
        "--report",
        output / (name + "-verification.json"),
    )
    print(
        json.dumps({"package": str(dmg), "sha256": checksum, "apple_notarized": False}),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arch", choices=("arm64", "x86_64"), required=True)
    build(parser.parse_args().arch)
