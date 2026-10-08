"""Exercise the real packager's asset resolver without running macOS tools."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("arch", ["arm64", "x86_64"])
def test_macos_assets_resolve_from_separate_spec_directory(tmp_path, monkeypatch, arch):
    cli = pytest.importorskip("PyInstaller.__main__")
    from PyInstaller.building.utils import format_binaries_and_datas

    source = Path(__file__).resolve().parents[1] / "scripts/build_macos.py"
    spec = importlib.util.spec_from_file_location("mac_builder_assets", source)
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)

    project = (tmp_path / "project with spaces").resolve()
    files = {
        "version.py": 'APP_VERSION = "3.5.0"\n',
        "run_desktop.py": "print('isolated packaging fixture')\n",
        "templates/index.html": "<p>Isolated template</p>",
        "static/script.js": "console.log('isolated asset');",
        "static/branding/mymovielist-logo.png": "mocked native icon input",
        "supabase/project.json": '{"url":"https://example.invalid"}',
        ".env": "PRIVATE_FIXTURE_DO_NOT_BUNDLE=true",
    }
    for name, content in files.items():
        target = project / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    monkeypatch.setattr(builder, "ROOT", project)
    # Keep the interpreter's real platform for SSL and PyInstaller internals.
    monkeypatch.setattr(
        builder, "sys", SimpleNamespace(platform="darwin", executable=sys.executable)
    )
    monkeypatch.setattr(builder.platform, "machine", lambda: arch)
    monkeypatch.setattr(builder.shutil, "which", lambda tool: f"/usr/bin/{tool}")
    monkeypatch.setenv("MACOSX_DEPLOYMENT_TARGET", "15.0")
    commands = []

    class ReachedPackager(Exception):
        pass

    def native_command(*args, **kwargs):
        command = [str(arg) for arg in args]
        if command[1:3] == ["-m", "PyInstaller"]:
            commands.append(command)
            raise ReachedPackager
        return ""

    monkeypatch.setattr(builder, "run", native_command)
    with pytest.raises(ReachedPackager):
        builder.build(arch)

    options = cli.generate_parser().parse_args(commands[0][3:])
    assert Path(options.specpath) == project / "build/macos" / arch
    assert options.target_arch == arch
    # PyInstaller resolves relative data sources from the generated .spec folder.
    # Calling its resolver reproduces the hosted build failure before this fix.
    resolved = format_binaries_and_datas(options.datas, workingdir=options.specpath)
    expected = {
        (str(Path(name)), str(project / name))
        for name in files
        if name.startswith(("templates/", "static/", "supabase/"))
    }
    assert resolved == expected
    assert options.filenames == [str(project / "run_desktop.py")]
