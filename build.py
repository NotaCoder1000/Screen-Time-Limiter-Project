"""
build.py — Compiles all Screen Limiter components into standalone Windows .exe
files using PyInstaller, then places them in a  dist\ScreenLimiter  folder
ready to be picked up by the NSIS installer script.

Run from the project root:
    python build.py

Requirements:
    pip install pyinstaller  (in addition to the usual requirements.txt deps)

Output:
    dist\ScreenLimiter\
        enforcer.exe — Background monitor (console, needs to call win32 APIs)
        popup.exe    — Interception popup (windowed, no console)
        tray.exe     — System tray icon  (windowed, no console)
        main.exe     — Combined control panel UI (windowed)
"""

import subprocess
import sys
import os
import shutil

ROOT     = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(ROOT, "dist", "ScreenLimiter")

# ── Build targets ──────────────────────────────────────────────────────────────
# Each entry: (script, output_name, windowed)
# windowed=True  → no console window  (--noconsole)
# windowed=False → console app        (needed for the service)
TARGETS = [
    ("enforcer.py", "enforcer", False),
    ("popup.py",    "popup",    True),
    ("tray.py",     "tray",     True),
    ("main_ui.py",  "main",     True),
]

# ── Hidden imports required by each module ─────────────────────────────────────
# PyInstaller's static analyser can't always see dynamic imports (e.g. wmi,
# win32com internals, customtkinter themes).  List them explicitly here.
HIDDEN_IMPORTS = [
    "wmi",
    "win32con",
    "win32process",
    "win32api",
    "pywintypes",
    "customtkinter",
    "psutil",
    "requests",
    "bcrypt",
    "pystray._win32",         # pystray Windows backend
    "PIL._tkinter_finder",
    # Encoding modules
    "encodings",
    "encodings.utf_8",
    "encodings.ascii",
    "encodings.latin_1",
    "encodings.cp1252",
    "encodings.idna",
    # urllib3 / requests — PyInstaller misses these with urllib3 v2
    "urllib3",
    "urllib3.util",
    "urllib3.util.retry",
    "urllib3.util.url",
    "urllib3.contrib",
    "urllib3.packages",
    "urllib3.packages.six",
    "urllib3.packages.six.moves",
    "urllib3.packages.six.moves.urllib",
    "charset_normalizer",
    "charset_normalizer.md__mypyc",
    "idna",
    "certifi",
]

# customtkinter ships theme JSON files that must be bundled as data
import customtkinter
CTK_DIR = os.path.dirname(customtkinter.__file__)

# ── Helpers ────────────────────────────────────────────────────────────────────

def run(cmd: list[str]):
    print(f"\n>>> {' '.join(cmd)}\n")
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print(f"ERROR: command failed with code {result.returncode}")
        sys.exit(result.returncode)


def pyinstaller_cmd(script: str, name: str, windowed: bool) -> list[str]:
    # Find Python's encodings directory and bundle it explicitly.
    # This fixes "Failed to import encodings module" on some systems.
    import encodings as _enc
    enc_dir = os.path.dirname(_enc.__file__)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        f"--name={name}",
        "--onefile",                          # single .exe per component
        f"--distpath={DIST_DIR}",
        "--workpath=build_tmp",
        "--specpath=build_tmp",
        # Bundle customtkinter themes + assets
        f"--add-data={CTK_DIR};customtkinter",
        # Explicitly bundle the encodings package
        f"--add-data={enc_dir};encodings",
    ]

    if windowed:
        cmd.append("--noconsole")             # suppress black console window

    for h in HIDDEN_IMPORTS:
        cmd += ["--hidden-import", h]

    # pywin32 post-install hook path — needed for servicemanager to work
    import site
    for sp in site.getsitepackages():
        hook = os.path.join(sp, "pywin32_system32")
        if os.path.isdir(hook):
            cmd += [f"--add-binary={hook}\\*.dll;."]
            break

    cmd.append(script)
    return cmd


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Screen Limiter - PyInstaller build")
    print("=" * 60)

    # Clean previous dist output for our app (leave other dist folders alone)
    if os.path.isdir(DIST_DIR):
        print(f"\nCleaning {DIST_DIR}...")
        shutil.rmtree(DIST_DIR)
    os.makedirs(DIST_DIR, exist_ok=True)

    for script, name, windowed in TARGETS:
        print(f"\n{'-'*60}")
        print(f"  Building {name}.exe  ({'windowed' if windowed else 'console'})")
        print(f"{'-'*60}")
        run(pyinstaller_cmd(script, name, windowed))

    # Clean up PyInstaller work folder
    work = os.path.join(ROOT, "build_tmp")
    if os.path.isdir(work):
        shutil.rmtree(work)

    print("\n" + "=" * 60)
    print("  Build complete!")
    print(f"  Output: {DIST_DIR}")
    print()
    print("  Next step: compile the NSIS installer")
    print('  Open installer.nsi in NSIS, click "Compile NSI scripts"')
    print("  or run:  makensis installer.nsi")
    print("=" * 60)


if __name__ == "__main__":
    main()
