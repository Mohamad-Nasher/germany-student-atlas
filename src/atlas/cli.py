"""Command line entry point:  atlas build | atlas sample | atlas analyze"""

from __future__ import annotations

import argparse
import sys

from .config import load_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="atlas", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="fetch every source and rebuild docs/data")
    b.add_argument("--offline", action="store_true", help="use only data/manual, no network")
    b.add_argument("--strict", action="store_true",
                   help="exit non-zero if any source failed (used by the scheduled job)")
    sub.add_parser("sample", help="write clearly-labelled synthetic preview data")
    sub.add_parser("analyze", help="run the cross-city regressions")
    args = parser.parse_args(argv)
    settings = load_settings()

    if args.command == "sample":
        from .sample import make
        make(settings)
        print("Wrote SYNTHETIC preview data to docs/data (flagged as sample).")
        return 0
    if args.command == "analyze":
        from .analysis import run
        return run()

    from .build import build
    meta = build(settings, offline=args.offline)
    failed = []
    for name, layer in meta["layers"].items():
        print(f"  {name:11s} {layer['status']:8s} {layer['detail']}")
        if layer["status"] == "error":
            failed.append(name)
    if failed and args.strict:
        print(f"Failed sources: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
