import ipaddress
import json
import os
from pathlib import Path
from types import SimpleNamespace

import conftest
import pytest
import regnet
import options
import essentials


def test_mainnet_seed_lists_are_curated_public_peers():
    def repo_git(file):
        import subprocess
        return subprocess.run(
            ["git", "-C", str(repository), "show", f"HEAD:{file}"],
            capture_output=True, text=True, check=True
        ).stdout
    repository = Path(__file__).parents[1]
    # Read the committed static seed lists (observer node may mutate the local
    # files at runtime while running, so test the curated repo version).
    peers = json.loads(repo_git("peers.txt"))
    suggested = json.loads(repo_git("suggested_peers.txt"))
    addresses = [ipaddress.ip_address(ip) for ip in peers]

    assert peers == suggested
    assert len(peers) == 9
    assert set(peers.values()) == {"5658"}
    assert all(
        address.version == 4 and address.is_global and not address.is_multicast
        for address in addresses
    )


def test_readme_lists_live_terranbase_explorer():
    readme = (Path(__file__).parents[1] / "README.md").read_text()

    assert "https://bismuth1.terranbase.xyz" in readme


def test_node_cli_accepts_explicit_config_and_regnet_dir(tmp_path):
    from node_cli import parse_node_args

    config_path = tmp_path / "regnet.conf"
    regnet_dir = tmp_path / "regnet"
    wallet_file = regnet_dir / "wallet.der"

    args = parse_node_args([
        "--config-custom",
        str(config_path),
        "--regnet-dir",
        str(regnet_dir),
        "--wallet-file",
        str(wallet_file),
        "--bind",
        "127.0.0.1",
        "--readiness-token",
        "test-token",
    ])

    assert args.config_custom == config_path.resolve()
    assert args.regnet_dir == regnet_dir.resolve()
    assert args.wallet_file == wallet_file.resolve()
    assert args.bind == "127.0.0.1"
    assert args.readiness_token == "test-token"


def test_configure_data_dir_isolates_regnet_files(tmp_path):
    data_dir = tmp_path / "regnet"

    regnet.configure_data_dir(data_dir)

    assert Path(regnet.REGNET_DB) == data_dir / "regmode.db"
    assert Path(regnet.REGNET_INDEX) == data_dir / "index_reg.db"
    assert Path(regnet.REGNET_PEERS) == data_dir / "peers_reg.txt"
    assert Path(regnet.REGNET_SUGGESTED_PEERS) == data_dir / "peers_reg.txt"
    assert regnet.FILES_TO_REMOVE == [regnet.REGNET_DB, regnet.REGNET_INDEX]


def test_options_loads_explicit_custom_config_without_chdir(tmp_path):
    base = tmp_path / "config.txt"
    custom = tmp_path / "regnet.txt"
    base.write_text("port=5658\nversion=mainnet0022\n")
    custom.write_text("port=3030\nversion=regnet\nregnet=True\n")

    config = options.Get()
    config.read(config_file=base, custom_config_file=custom)

    assert config.port == "3030"
    assert config.version == "regnet"
    assert config.regnet is True


def test_options_rejects_missing_explicit_custom_config(tmp_path):
    base = tmp_path / "config.txt"
    base.write_text("port=5658\nversion=mainnet0022\n")

    with pytest.raises(FileNotFoundError):
        options.Get().read(
            config_file=base,
            custom_config_file=tmp_path / "missing-regnet.txt",
        )


def test_explicit_wallet_ignores_legacy_keys_in_working_directory(tmp_path, monkeypatch):
    class SilentLog:
        def info(self, _message):
            pass

        def warning(self, _message):
            pass

    monkeypatch.chdir(tmp_path)
    (tmp_path / "privkey.der").write_text("legacy-key-must-not-win")
    wallet_file = tmp_path / "isolated" / "wallet.der"
    wallet_file.parent.mkdir()

    essentials.keys_check(SilentLog(), str(wallet_file), allow_legacy=False)

    assert wallet_file.is_file()


def test_regnet_application_log_is_inside_data_dir(tmp_path):
    from node_cli import application_log_path

    data_dir = tmp_path / "regnet"

    assert application_log_path(data_dir) == data_dir.resolve() / "node.log"
    assert application_log_path(None) == Path("node.log")


def test_network_paths_are_set_before_destructive_ledger_handling():
    node_source = (Path(__file__).parents[1] / "node.py").read_text()

    setup_position = node_source.index("    setup_net_type()", node_source.index("if __name__"))
    removal_position = node_source.index("    if not node.full_ledger")

    assert setup_position < removal_position


def test_explicit_wallet_disables_legacy_windows_migration():
    node_source = (Path(__file__).parents[1] / "node.py").read_text()

    migration_guard = (
        'if cli_args.wallet_file is None and os.path.exists("../wallet.der")'
    )
    assert migration_guard in node_source


def test_node_cli_accepts_legacy_regnet_positional_argument():
    from node_cli import parse_node_args

    args = parse_node_args(["regnet2"])

    assert args.legacy_mode == "regnet2"


def test_legacy_regnet_mode_requires_explicit_isolation():
    from node_cli import parse_node_args, validate_runtime_args

    args = parse_node_args(["regnet2"])

    with pytest.raises(ValueError, match="--regnet-dir"):
        validate_runtime_args(
            args,
            SimpleNamespace(regnet=False, version="mainnet0022"),
        )


def test_regnet_data_dir_cannot_fall_back_to_mainnet(tmp_path):
    from node_cli import parse_node_args, validate_runtime_args

    args = parse_node_args(["--regnet-dir", str(tmp_path / "regnet")])

    with pytest.raises(ValueError, match="requires --config-custom"):
        validate_runtime_args(args, SimpleNamespace(regnet=False))


def test_regnet_config_rejects_mainnet_version(tmp_path):
    from node_cli import parse_node_args, validate_runtime_args

    config_path = tmp_path / "regnet.conf"
    args = parse_node_args([
        "--config-custom",
        str(config_path),
        "--regnet-dir",
        str(tmp_path / "regnet"),
    ])

    with pytest.raises(ValueError, match="version=regnet"):
        validate_runtime_args(
            args,
            SimpleNamespace(regnet=True, version="mainnet0022"),
        )


def test_regnet_rejects_non_loopback_bind(tmp_path):
    from node_cli import parse_node_args, validate_runtime_args

    args = parse_node_args([
        "--config-custom",
        str(tmp_path / "regnet.conf"),
        "--regnet-dir",
        str(tmp_path / "regnet"),
        "--bind",
        "0.0.0.0",
    ])

    with pytest.raises(ValueError, match="loopback"):
        validate_runtime_args(
            args,
            SimpleNamespace(regnet=True, version="regnet"),
        )


def test_regnet_config_alone_cannot_bind_publicly(tmp_path):
    from node_cli import parse_node_args, validate_runtime_args

    config_path = tmp_path / "regnet.conf"
    config_path.touch()
    args = parse_node_args([
        "--config-custom",
        str(config_path),
        "--bind",
        "0.0.0.0",
    ])

    with pytest.raises(ValueError, match="loopback"):
        validate_runtime_args(
            args,
            SimpleNamespace(regnet=True, version="regnet"),
        )


def test_regnet_rejects_empty_bind(tmp_path):
    from node_cli import parse_node_args, validate_runtime_args

    config_path = tmp_path / "regnet.conf"
    config_path.touch()
    args = parse_node_args([
        "--config-custom",
        str(config_path),
        "--regnet-dir",
        str(tmp_path / "regnet"),
        "--bind",
        "",
    ])

    with pytest.raises(ValueError, match="loopback"):
        validate_runtime_args(
            args,
            SimpleNamespace(regnet=True, version="regnet"),
        )


def test_regnet_rejects_empty_readiness_token(tmp_path):
    from node_cli import parse_node_args, validate_runtime_args

    config_path = tmp_path / "regnet.conf"
    config_path.touch()
    args = parse_node_args([
        "--config-custom",
        str(config_path),
        "--regnet-dir",
        str(tmp_path / "regnet"),
        "--readiness-token",
        "",
    ])

    with pytest.raises(ValueError, match="non-empty"):
        validate_runtime_args(
            args,
            SimpleNamespace(regnet=True, version="regnet"),
        )


def test_regnet_wallet_defaults_inside_data_dir(tmp_path):
    from node_cli import parse_node_args, wallet_path

    regnet_dir = tmp_path / "regnet"
    args = parse_node_args(["--regnet-dir", str(regnet_dir)])

    assert wallet_path(args) == regnet_dir.resolve() / "wallet.der"


def test_regnet_rejects_wallet_outside_data_dir(tmp_path):
    from node_cli import parse_node_args, validate_runtime_args

    config_path = tmp_path / "regnet.conf"
    config_path.touch()
    args = parse_node_args([
        "--config-custom",
        str(config_path),
        "--regnet-dir",
        str(tmp_path / "regnet"),
        "--wallet-file",
        str(tmp_path / "mainnet-wallet.der"),
    ])

    with pytest.raises(ValueError, match="inside --regnet-dir"):
        validate_runtime_args(
            args,
            SimpleNamespace(regnet=True, version="regnet"),
        )


@pytest.mark.parametrize(
    "unsafe_dir",
    [Path.cwd(), Path.cwd().parent, Path.cwd() / ".regnet-test"],
)
def test_regnet_rejects_working_tree_overlap(unsafe_dir):
    from node_cli import parse_node_args, validate_runtime_args

    args = parse_node_args([
        "--config-custom",
        str(Path(__file__).parent / "config_custom.txt"),
        "--regnet-dir",
        str(unsafe_dir),
    ])

    with pytest.raises(ValueError, match="dedicated.*working directory"):
        validate_runtime_args(
            args,
            SimpleNamespace(regnet=True, version="regnet"),
        )


def test_regnet_defaults_to_loopback_bind():
    from node_cli import bind_host, parse_node_args

    args = parse_node_args([])

    assert bind_host(args, SimpleNamespace(regnet=True)) == "127.0.0.1"
    assert bind_host(args, SimpleNamespace(regnet=False)) == "0.0.0.0"


def test_launch_failure_removes_temporary_directory(tmp_path, monkeypatch):
    regnet_dir = tmp_path / "regnet"
    regnet_dir.mkdir()

    def fail_to_spawn(*_args, **_kwargs):
        raise OSError("spawn failed")

    monkeypatch.setattr(conftest, "Popen", fail_to_spawn)

    with pytest.raises(OSError, match="spawn failed"):
        conftest.launch_regnet(["python", "node.py"], regnet_dir)

    assert not regnet_dir.exists()


def test_output_open_interrupt_removes_temporary_directory(tmp_path, monkeypatch):
    regnet_dir = tmp_path / "regnet"
    regnet_dir.mkdir()

    def interrupt_open(*_args, **_kwargs):
        raise KeyboardInterrupt()

    monkeypatch.setattr(Path, "open", interrupt_open)

    with pytest.raises(KeyboardInterrupt):
        conftest.launch_regnet(["python", "node.py"], regnet_dir)

    assert not regnet_dir.exists()


def test_test_wallet_environment_is_restored(monkeypatch):
    monkeypatch.setenv("BISMUTH_TEST_WALLET", "callers-wallet.der")

    previous = conftest.set_test_wallet_environment("temporary-wallet.der")
    assert os.environ["BISMUTH_TEST_WALLET"] == "temporary-wallet.der"

    conftest.restore_test_wallet_environment(previous)
    assert os.environ["BISMUTH_TEST_WALLET"] == "callers-wallet.der"


def test_fixture_reuses_standalone_lifecycle_primitives():
    import regnet_control

    assert conftest.rpc_command is regnet_control.rpc_command
    assert conftest.wait_for_regnet is regnet_control.wait_for_regnet
    assert conftest.stop_regnet is regnet_control.stop_regnet_process


def test_cleanup_continues_when_stop_raises(tmp_path, monkeypatch):
    regnet_dir = tmp_path / "regnet"
    regnet_dir.mkdir()
    output_path = regnet_dir / "node-output.log"
    node_output = output_path.open("w+")
    monkeypatch.setenv("BISMUTH_TEST_WALLET", "temporary-wallet.der")
    previous = (True, "callers-wallet.der")

    def fail_to_stop(_process):
        raise RuntimeError("stop failed")

    monkeypatch.setattr(conftest, "stop_regnet", fail_to_stop)

    with pytest.raises(RuntimeError, match="stop failed"):
        conftest.cleanup_regnet(object(), node_output, previous, regnet_dir)

    assert node_output.closed
    assert os.environ["BISMUTH_TEST_WALLET"] == "callers-wallet.der"
    assert not regnet_dir.exists()


def test_fixture_cleans_token_generation_interrupt(tmp_path, monkeypatch):
    regnet_dir = tmp_path / "regnet"

    class FakeFactory:
        @staticmethod
        def mktemp(_name):
            regnet_dir.mkdir()
            return regnet_dir

    def interrupt_token(_length):
        raise KeyboardInterrupt()

    monkeypatch.setattr(conftest, "ensure_regnet_port_available", lambda: None)
    monkeypatch.setattr(conftest.secrets, "token_hex", interrupt_token)
    fixture = conftest.myserver.__wrapped__(FakeFactory())

    with pytest.raises(KeyboardInterrupt):
        next(fixture)

    assert not regnet_dir.exists()


def test_generate_blocks_retries_failed_generation(monkeypatch):
    class EmptyMempool:
        @staticmethod
        def fetchall(_query):
            return []

    generated_from = []
    results = iter([None, "block-1", "block-2"])

    def generate(blockhash, _mempool_txs, _node, _db_handler):
        generated_from.append(blockhash)
        return next(results)

    monkeypatch.setattr(regnet, "generate_one_block", generate)
    monkeypatch.setattr(regnet.mp, "MEMPOOL", EmptyMempool())

    result = regnet.generate_blocks("genesis", 2, None, None)

    assert result == "block-2"
    assert generated_from == ["genesis", "genesis", "block-1"]


def test_generate_blocks_rejects_negative_count():
    with pytest.raises(ValueError, match="non-negative"):
        regnet.generate_blocks("genesis", -1, None, None)


def test_generate_blocks_bounds_nonce_search(monkeypatch):
    class EmptyMempool:
        @staticmethod
        def fetchall(_query):
            return []

    class SilentLog:
        def warning(self, *_args):
            pass

    node = SimpleNamespace(
        heavy=False,
        logger=SimpleNamespace(app_log=SilentLog()),
    )
    monkeypatch.setattr(regnet.mp, "MEMPOOL", EmptyMempool())
    monkeypatch.setattr(regnet, "MAX_NONCE_BATCHES", 1, raising=False)
    monkeypatch.setattr(regnet, "MAX_GENERATION_ATTEMPTS", 2)
    monkeypatch.setattr(
        regnet.mining,
        "anneal3_regnet",
        lambda *_args: "zzzz",
    )

    with pytest.raises(RuntimeError, match="after 2 attempts"):
        regnet.generate_blocks("a-blockhash", 1, node, object())


def test_regnet_command_returns_generation_error(monkeypatch):
    responses = []
    logger = SimpleNamespace(
        app_log=SimpleNamespace(warning=lambda *_args: None),
    )
    node = SimpleNamespace(logger=logger)

    monkeypatch.setattr(regnet.connections, "receive", lambda _socket: -1)
    monkeypatch.setattr(
        regnet.connections,
        "send",
        lambda _socket, response: responses.append(response),
    )

    regnet.command(object(), "regtest_generate", "genesis", node, None)

    assert responses == ["ERROR: Regnet block count must be non-negative"]
