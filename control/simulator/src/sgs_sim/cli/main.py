"""``sgs-sim`` CLI entry point — SIMULATED telemetry sender.

SIMULATED telemetry. Streams CCSDS/PUS HK + event packets over UDP into Yamcs.
This is NOT operational software; the telemetry is synthetic but CCSDS/PUS-compliant
in structure (see ``PACKET_FORMAT.md``).
"""

from __future__ import annotations

import argparse
import logging
import sys

from sgs_sim.config import SimConfig, default_config_path, load
from sgs_sim.sender import run_loop

logger = logging.getLogger("sgs_sim")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sgs-sim",
        description="SIMULATED spacecraft simulator — emits CCSDS/PUS telemetry over UDP "
        "into Yamcs. NOT operational.",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="path to a TOML config file (default: shipped config/default.toml)",
    )
    parser.add_argument("--host", default=None, help="UDP TM target host (overrides config)")
    parser.add_argument(
        "--port", type=int, default=None, help="UDP TM target port (overrides config)"
    )
    parser.add_argument("--tc-host", default=None, help="TC receiver bind host (overrides config)")
    parser.add_argument(
        "--tc-port", type=int, default=None, help="TC receiver bind port (overrides config)"
    )
    parser.add_argument(
        "--no-tc",
        action="store_true",
        help="disable the telecommand receiver (run TM-only)",
    )
    parser.add_argument(
        "--rate", type=float, default=None, help="emit rate in Hz (overrides config)"
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=0.0,
        help="run time in seconds; 0 = forever (default: 0)",
    )
    parser.add_argument("--seed", type=int, default=None, help="RNG seed (overrides config)")
    return parser


def _load_config(config_arg: str | None) -> SimConfig:
    path = config_arg if config_arg is not None else default_config_path()
    return load(path)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        config = _load_config(args.config)
    except (OSError, ValueError) as exc:
        logger.error("failed to load config: %s", exc)
        return 2

    config = config.with_overrides(
        host=args.host,
        port=args.port,
        tc_host=args.tc_host,
        tc_port=args.tc_port,
        rate_hz=args.rate,
        seed=args.seed,
    )

    enable_tc = not args.no_tc
    logger.warning(
        "SIMULATED telemetry -> %s:%d (CCSDS/PUS, NOT operational) | rate=%.3g Hz seed=%d "
        "duration=%s | TC receiver %s",
        config.host,
        config.port,
        config.rate_hz,
        config.seed,
        "forever" if args.duration <= 0 else f"{args.duration:g}s",
        f"on {config.tc_host}:{config.tc_port}" if enable_tc else "off",
    )

    try:
        hk_count = run_loop(config, duration=args.duration, enable_tc=enable_tc)
    except KeyboardInterrupt:
        logger.info("interrupted; stopping SIMULATED telemetry")
        return 0

    logger.info("SIMULATED run complete: emitted %d HK packets", hk_count)
    return 0


if __name__ == "__main__":
    sys.exit(main())
