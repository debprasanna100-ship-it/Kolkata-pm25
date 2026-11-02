"""Command line entry point.

    python -m pm25.cli build     # collect/assemble the dataset
    python -m pm25.cli train     # baselines + GBDT + LOSO
    python -m pm25.cli explain   # SHAP + source proxies
    python -m pm25.cli app       # launch the dashboard
    python -m pm25.cli all       # build -> train -> explain
"""

from __future__ import annotations

import argparse
import sys

from .config import Config
from .utils import get_logger, set_seed

log = get_logger("pm25.cli")


def _parser() -> argparse.ArgumentParser:
    # --config/--root are accepted both before and after the subcommand:
    # the parent parser carries SUPPRESS defaults so a subcommand occurrence
    # overrides the global one without erasing it (argparse would otherwise
    # let the subparser's default clobber the value parsed earlier).
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default=argparse.SUPPRESS, help="path to config.yaml")
    common.add_argument("--root", default=argparse.SUPPRESS, help="project root (defaults to cwd)")

    parser = argparse.ArgumentParser(
        prog="pm25",
        description="Hourly PM2.5 estimation and source attribution for Kolkata",
    )
    parser.add_argument("--config", default=None, help="path to config.yaml")
    parser.add_argument("--root", default=None, help="project root (defaults to cwd)")

    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="assemble the dataset", parents=[common])
    build.add_argument("--mode", choices=["demo", "live"], default=None,
                       help="override data.mode")
    build.add_argument("--start", default=None)
    build.add_argument("--end", default=None)

    train = sub.add_parser("train", help="train and evaluate models", parents=[common])
    train.add_argument("--horizons", default=None,
                       help="comma separated, e.g. 0,1,6,24")
    train.add_argument("--test-year", type=int, default=None)
    train.add_argument("--no-loso", action="store_true", help="skip leave-one-station-out")
    train.add_argument("--deep", action="store_true", help="also train the LSTM (needs torch)")
    train.add_argument("--quick", action="store_true", help="fewer trees, no LOSO")

    sub.add_parser("explain", help="SHAP + source proxy agreement", parents=[common])

    app = sub.add_parser("app", help="launch the Streamlit dashboard", parents=[common])
    app.add_argument("--port", type=int, default=8501)

    sub.add_parser("all", help="build -> train -> explain", parents=[common])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    cfg = Config.load(args.config, args.root)
    set_seed(int(cfg.get("project.seed", 42)))

    if args.command == "build":
        if args.mode:
            cfg.set("data.mode", args.mode)
        if args.start:
            cfg.set("data.start", args.start)
        if args.end:
            cfg.set("data.end", args.end)
        from .data import build

        build.build(cfg)
        return 0

    if args.command == "train":
        from .models import train as trainer

        horizons = None
        if args.horizons:
            horizons = [int(h.strip()) for h in args.horizons.split(",") if h.strip()]

        if args.quick:
            cfg.set("models.gbdt.n_estimators", 120)

        trainer.run(
            cfg,
            horizons=horizons,
            test_year=args.test_year,
            with_loso=not args.no_loso and not args.quick,
            with_deep=args.deep,
            quick=args.quick,
        )
        return 0

    if args.command == "explain":
        from .explain import attribution

        attribution.run(cfg)
        return 0

    if args.command == "all":
        from .data import build as builder
        from .explain import attribution
        from .models import train as trainer

        builder.build(cfg)
        trainer.run(cfg)
        attribution.run(cfg)
        return 0

    if args.command == "app":
        import subprocess
        from pathlib import Path

        dashboard = Path(__file__).parent / "app" / "dashboard.py"
        cmd = [
            sys.executable, "-m", "streamlit", "run", str(dashboard),
            "--server.port", str(args.port),
        ]
        log.info("launching dashboard: %s", " ".join(cmd))
        return subprocess.call(cmd)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
