# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — QuMail backend (onedir).

Build from the repo root:

    pyinstaller packaging/backend.spec

Produces ``dist/qumail-backend/qumail-backend(.exe)``. Ship a ``.env`` beside
the executable (it is read from the working directory, never bundled — no
secrets in the build).
"""

import os

from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.dirname(os.path.abspath(SPECPATH))  # repo root (spec lives in packaging/)

hidden = (
    collect_submodules("uvicorn")
    + collect_submodules("backend")
    + ["pydantic", "pydantic_settings", "Crypto"]
)

a = Analysis(
    [os.path.join(SPECPATH, "backend_entry.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[],
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["qiskit", "qiskit_aer", "electron"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="qumail-backend",
    console=True,
    disable_windowed_traceback=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="qumail-backend")
