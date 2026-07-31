# PyInstaller spec for Medication Adherence Dashboard
# Build: pyinstaller MedicationDashboard.spec
# Before building: run "cd frontend && npm run build" so frontend/build exists
# Output: single exe that runs on any Windows machine (no Python required)

import sys

# Data files to bundle (relative to project root). They are extracted to _MEIPASS at runtime.
def _datas():
    from pathlib import Path
    base = Path(".")
    out = []
    if (base / "templates").is_dir():
        out.append(("templates", "templates"))
    if (base / "frontend" / "build").is_dir():
        out.append(("frontend/build", "frontend/build"))
    return out

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=_datas(),
    hiddenimports=[
        "flask",
        "flask_cors",
        "flask_socketio",
        "flask.json",
        "werkzeug",
        "werkzeug.serving",
        "jinja2",
        "markupsafe",
        "itsdangerous",
        "click",
        "engineio",
        "engineio.async_drivers.threading",
        "socketio",
        "eventlet",
        "eventlet.hubs",
        "eventlet.hubs.hub",
        "eventlet.support",
        "eventlet.green",
        "eventlet.green.socket",
        "dotenv",
        "openpyxl",
        "openpyxl.cell._writer",
        "pandas",
        "numpy",
        "plotly",
        "plotly.graph_objs",
        "requests",
        "openai",
        "twilio",
        "twilio.rest",
        "runtime_paths",
        "config",
        "utils",
        "agent",
        "pharmacy",
        "structure",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "scipy",
        "numpy.distutils",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="MedicationDashboard",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Keep console so user sees "Starting... http://localhost:5000"
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
