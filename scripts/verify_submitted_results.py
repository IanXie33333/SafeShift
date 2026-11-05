"""Snapshot/verify the submitted result files, including figures, without rewriting them."""

import argparse
import hashlib
import json
from pathlib import Path


def inventory(root):
    files = set()
    for name in ["count_regression", "lightgbm_forecast"]:
        files.update(p for p in (root / "artifacts" / name).rglob("*") if p.is_file())
    for name in ["metrics", "figures"]:
        files.update(p for p in (root / "artifacts" / name).glob("nlp_package_c_*") if p.is_file())
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(files)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["snapshot", "verify"])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    current = inventory(args.root.resolve())
    if not current:
        raise SystemExit("No submitted result files found; merge the three PRs first")
    if args.action == "snapshot":
        args.manifest.write_text(json.dumps(current, indent=2) + "\n")
    elif current != json.loads(args.manifest.read_text()):
        raise SystemExit("Submitted results changed or files were added/removed in protected folders")
    print(f"{args.action}: {len(current)} submitted result files accounted for")


if __name__ == "__main__":
    main()
