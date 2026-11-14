import argparse
import json
from dataclasses import asdict

from .core import clean, preview


def main():
    parser = argparse.ArgumentParser(description="EQLog · backup-first Legends log cleanup")
    parser.add_argument("path", nargs="?", help="Log to preview; omit to open the desktop app")
    parser.add_argument("--apply", action="store_true", help="Back up and clean the selected log")
    parser.add_argument("--offline", action="store_true", help="Confirm EverQuest and Companion are closed")
    parser.add_argument("--smoke-test", metavar="RESULT_JSON", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.smoke_test:
        from .smoke import run
        raise SystemExit(run(args.smoke_test))
    if not args.path:
        if args.apply or args.offline:
            parser.error("A log path is required with command-line options")
        from .app import main as gui
        gui()
        return
    try:
        report = clean(args.path, offline=args.offline) if args.apply else preview(args.path)
    except Exception as exc:
        parser.exit(1, f"EQLog: {exc}\n")
    print(json.dumps(asdict(report) | {"saved_bytes": report.saved_bytes, "reduction": report.reduction},
                     default=str, indent=2))


if __name__ == "__main__":
    main()
