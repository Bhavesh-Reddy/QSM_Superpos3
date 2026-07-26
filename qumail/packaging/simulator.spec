# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — QuMail KM simulator (onedir).

Build from the repo root:

    pyinstaller packaging/simulator.spec

Produces ``dist/qumail-simulator/qumail-simulator(.exe)``. Qiskit is optional
(the QRNG falls back to the OS CSPRNG); if it is installed and you want the
quantum path bundled, remove it from ``excludes`` below.
"""

import os

from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.dirname(os.path.abspath(SPECPATH))

hidden = collect_submodules("uvicorn") + collect_submodules("km_simulator")

a = Analysis(
    [os.path.join(SPECPATH, "simulator_entry.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[],
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["qiskit", "qiskit_aer"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="qumail-simulator",
    console=True,
    disable_windowed_traceback=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="qumail-simulator")
