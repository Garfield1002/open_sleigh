import shutil
import sys
import tempfile
from pathlib import Path
from subprocess import run

PROCESSORS_SUBPATH = Path("Ghidra/Processors")
LANGUAGES_LEAF = Path("data/languages")


def discover_processors(ghidra_root: Path) -> list[str]:
    processors_dir = ghidra_root / PROCESSORS_SUBPATH

    if not processors_dir.is_dir():
        sys.exit(f"ERROR: Not a Ghidra root (missing {processors_dir})")

    names = [
        c.name
        for c in sorted(processors_dir.iterdir())
        if c.is_dir() and (c / LANGUAGES_LEAF).is_dir()
    ]

    if not names:
        sys.exit(f"ERROR: No processors found under {processors_dir}")

    return names


def filter_processors_history(
    repo_root: Path, processors: list[str], *, force: bool = False
):
    cmd = ["git", "filter-repo"]

    for processor in processors:
        src = PROCESSORS_SUBPATH / processor / LANGUAGES_LEAF
        dst = Path("src") / processor

        src_filter = f"{src.as_posix()}/"
        dst_prefix = f"{dst.as_posix()}/"

        cmd.extend(
            [
                "--path",
                src_filter,
                "--path-rename",
                f"{src_filter}:{dst_prefix}",
            ]
        )

    if force:
        cmd.append("--force")

    print("+", " ".join(cmd))
    run(cmd, cwd=repo_root, check=True)


def copy_filtered_repo_into_current_dir(ghidra_root: Path, repo_root: Path):
    processors = discover_processors(ghidra_root)

    with tempfile.TemporaryDirectory(prefix="ghidra-filter-") as tmp:
        tmp_repo = Path(tmp) / "repo"

        run(
            ["git", "clone", "--no-local", str(ghidra_root), str(tmp_repo)],
            check=True,
        )

        filter_processors_history(tmp_repo, processors)

        for item in tmp_repo.iterdir():
            shutil.move(str(item), repo_root / item.name)


if __name__ == "__main__":
    ghidra_root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    repo_root = Path.cwd().resolve()

    copy_filtered_repo_into_current_dir(ghidra_root, repo_root)
