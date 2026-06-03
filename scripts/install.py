#!/usr/bin/env python3
"""Deploy Open SLEIGH specs into a Ghidra installation (no Ghidra recompile).

SLEIGH specs are data, not part of Ghidra's compiled code. This script copies
the repo's per-processor language files into a Ghidra install and compiles the
.slaspec sources to .sla using the bundled `support/sleigh` compiler (which runs
the already-built Ghidra jars -- it does NOT rebuild Ghidra).

Usage:
    python scripts/install.py [GHIDRA_ROOT] [options]

    GHIDRA_ROOT   Path to a Ghidra install. Defaults to $GHIDRA_INSTALL_DIR.

Options:
    --only P1,P2  Only deploy the named processors (comma-separated).
    --no-compile  Skip the sleigh pre-compile step (Ghidra recompiles lazily).
    --no-backup   Do not back up files that get overwritten.
    --dry-run     Print actions without changing anything.
"""

import argparse
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from subprocess import run

PROCESSORS_SUBPATH = Path("Ghidra/Processors")
LANGUAGES_LEAF = Path("data/languages")
BACKUP_ROOT_NAME = "open_sleigh_backup"
# Generated artifacts that become stale when a .slaspec is replaced.
STALE_SUFFIXES = (".sla", ".sla.xml")


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def discover_repo_processors(src_dir: Path) -> list[str]:
    if not src_dir.is_dir():
        sys.exit(f"ERROR: missing source directory {src_dir}")
    names = [c.name for c in sorted(src_dir.iterdir()) if c.is_dir()]
    if not names:
        sys.exit(f"ERROR: no processors found under {src_dir}")
    return names


def resolve_ghidra_root(arg: str | None) -> Path:
    raw = arg or os.environ.get("GHIDRA_INSTALL_DIR")
    if not raw:
        sys.exit(
            "ERROR: no Ghidra root given and $GHIDRA_INSTALL_DIR is unset.\n"
            "       Pass it as the first argument: install.py /path/to/ghidra"
        )
    root = Path(raw).resolve()
    if not (root / PROCESSORS_SUBPATH).is_dir():
        sys.exit(f"ERROR: not a Ghidra root (missing {root / PROCESSORS_SUBPATH})")
    sleigh = root / "support" / "sleigh"
    if not sleigh.is_file():
        sys.exit(f"ERROR: bundled SLEIGH compiler not found at {sleigh}")
    return root


def iter_src_files(proc_src: Path):
    """Yield (file, relative_path) for every file under a processor src dir."""
    for path in sorted(proc_src.rglob("*")):
        if path.is_file():
            yield path, path.relative_to(proc_src)


def deploy_processor(
    proc: str,
    proc_src: Path,
    ghidra_root: Path,
    backup_dir: Path | None,
    dry_run: bool,
) -> bool:
    """Copy one processor's files into the install. Returns True if it's a new module."""
    module_dir = ghidra_root / PROCESSORS_SUBPATH / proc
    languages_dir = module_dir / LANGUAGES_LEAF
    is_new_module = not module_dir.is_dir()

    if is_new_module:
        print(f"  [new module] creating {module_dir}")
        if not dry_run:
            languages_dir.mkdir(parents=True, exist_ok=True)
            # Empty marker file: how Ghidra discovers a processor module.
            (module_dir / "Module.manifest").touch()
    elif not dry_run:
        languages_dir.mkdir(parents=True, exist_ok=True)

    for src_file, rel in iter_src_files(proc_src):
        dst_file = languages_dir / rel

        if backup_dir is not None and dst_file.exists():
            _backup(dst_file, ghidra_root, backup_dir, dry_run)

        # When replacing a .slaspec, also back up + remove its stale .sla outputs
        # so a failed recompile can't leave an old binary shadowing new source.
        if backup_dir is not None and src_file.suffix == ".slaspec":
            for suffix in STALE_SUFFIXES:
                stale = dst_file.with_suffix(suffix)
                if stale.exists():
                    _backup(stale, ghidra_root, backup_dir, dry_run)

        print(f"  copy {rel}")
        if not dry_run:
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)  # copy2 preserves mtime

    return is_new_module


def _backup(target_file: Path, ghidra_root: Path, backup_dir: Path, dry_run: bool):
    rel = target_file.relative_to(ghidra_root)
    dest = backup_dir / rel
    print(f"  backup {rel}")
    if not dry_run:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target_file, dest)


def compile_processor(proc: str, ghidra_root: Path, dry_run: bool) -> bool:
    """Compile every .slaspec under a processor's languages dir. Returns success."""
    sleigh = ghidra_root / "support" / "sleigh"
    languages_dir = ghidra_root / PROCESSORS_SUBPATH / proc / LANGUAGES_LEAF
    cmd = [str(sleigh), "-a", str(languages_dir)]
    print(f"  compile: {' '.join(cmd)}")
    if dry_run:
        return True
    result = run(cmd)
    return result.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ghidra_root", nargs="?", help="Ghidra install path")
    parser.add_argument("--only", help="comma-separated processors to deploy")
    parser.add_argument("--no-compile", action="store_true")
    parser.add_argument("--no-backup", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = repo_root()
    src_dir = root / "src"
    ghidra_root = resolve_ghidra_root(args.ghidra_root)

    processors = discover_repo_processors(src_dir)
    if args.only:
        wanted = [p.strip() for p in args.only.split(",") if p.strip()]
        unknown = sorted(set(wanted) - set(processors))
        if unknown:
            sys.exit(f"ERROR: unknown processor(s): {', '.join(unknown)}")
        processors = [p for p in processors if p in wanted]

    backup_dir = None
    if not args.no_backup:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_dir = ghidra_root / BACKUP_ROOT_NAME / stamp

    print(f"Ghidra root : {ghidra_root}")
    print(f"Processors  : {len(processors)} ({', '.join(processors)})")
    print(f"Backup dir  : {backup_dir or 'disabled'}")
    print(f"Mode        : {'DRY RUN' if args.dry_run else 'apply'}\n")

    new_modules: list[str] = []
    for proc in processors:
        print(f"== {proc} ==")
        if deploy_processor(proc, src_dir / proc, ghidra_root, backup_dir, args.dry_run):
            new_modules.append(proc)

    failures: list[str] = []
    if not args.no_compile:
        print("\n-- compiling --")
        for proc in processors:
            print(f"== {proc} ==")
            if not compile_processor(proc, ghidra_root, args.dry_run):
                failures.append(proc)

    print("\n========== summary ==========")
    print(f"Deployed     : {len(processors)} processor(s)")
    if new_modules:
        print(f"New modules  : {', '.join(new_modules)}")
    if backup_dir is not None and not args.dry_run and backup_dir.exists():
        print(f"Backup saved : {backup_dir}")
    if failures:
        print(f"FAILED       : {', '.join(failures)}")
        print("Some specs did not compile (community specs may be untested).")
        return 1
    print("All done." + (" (dry run)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
