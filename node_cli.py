"""Command-line options for starting a Bismuth node in test environments."""

import argparse
from ipaddress import ip_address
from pathlib import Path


def existing_path(value):
    """Return an absolute path without requiring it to exist at parse time."""
    if not value:
        raise argparse.ArgumentTypeError("Path options must be non-empty")
    return Path(value).expanduser().resolve()


def application_log_path(regnet_dir):
    """Place mutable node logs alongside isolated regnet state."""
    if regnet_dir is None:
        return Path("node.log")
    return existing_path(regnet_dir) / "node.log"


def validate_runtime_args(args, config):
    """Reject test-state options that could otherwise start a mainnet node."""
    if args.readiness_token is not None and not args.readiness_token:
        raise ValueError("--readiness-token must be non-empty")
    if args.regnet_dir is not None and args.config_custom is None:
        raise ValueError("--regnet-dir requires --config-custom")
    if args.legacy_mode is not None and args.regnet_dir is None:
        raise ValueError(
            "Legacy regnet mode requires explicit --config-custom and --regnet-dir"
        )
    regnet_requested = (
        bool(config.regnet)
        or args.regnet_dir is not None
        or args.readiness_token is not None
        or args.legacy_mode is not None
    )
    if args.regnet_dir is not None and not config.regnet:
        raise ValueError("--regnet-dir requires a config with regnet=True")
    if regnet_requested and config.version != "regnet":
        raise ValueError("Explicit regnet startup requires version=regnet")
    if args.readiness_token is not None and not config.regnet:
        raise ValueError("--readiness-token is only valid for regnet")
    if args.bind is not None:
        try:
            is_loopback = ip_address(args.bind).is_loopback
        except ValueError as exc:
            message = "Bind must be a numeric address"
            if regnet_requested:
                message = "Explicit regnet bind must be a numeric loopback address"
            raise ValueError(message) from exc
        if regnet_requested and not is_loopback:
            raise ValueError("Explicit regnet bind must be a loopback address")
    if regnet_requested and args.regnet_dir is None:
        raise ValueError("Regnet startup requires explicit --regnet-dir isolation")
    if args.regnet_dir is not None:
        data_dir = args.regnet_dir.resolve()
        working_dir = Path.cwd().resolve()
        if (
            data_dir == working_dir
            or data_dir.is_relative_to(working_dir)
            or working_dir.is_relative_to(data_dir)
        ):
            raise ValueError(
                "Regnet requires a dedicated directory outside the working directory tree"
            )
        isolated_wallet = wallet_path(args).resolve()
        if isolated_wallet == data_dir or not isolated_wallet.is_relative_to(data_dir):
            raise ValueError("Regnet wallet must be inside --regnet-dir")


def bind_host(args, config):
    if args.bind is not None:
        return args.bind
    return "127.0.0.1" if config.regnet else "0.0.0.0"


def wallet_path(args):
    if args.wallet_file:
        return args.wallet_file
    if args.regnet_dir:
        return args.regnet_dir / "wallet.der"
    return Path("wallet.der")


def parse_node_args(argv=None):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config-custom", type=existing_path)
    parser.add_argument("--regnet-dir", type=existing_path)
    parser.add_argument("--wallet-file", type=existing_path)
    parser.add_argument("--bind")
    parser.add_argument("--readiness-token")
    parser.add_argument("legacy_mode", nargs="?", choices=("regnet", "regnet2"))
    return parser.parse_args(argv)
