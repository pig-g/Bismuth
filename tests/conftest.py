import os
from pathlib import Path
import secrets
import shutil
import socket
from subprocess import STDOUT, Popen, TimeoutExpired
import sys
from time import monotonic, sleep

import connections
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
REGNET_CONFIG = Path(__file__).with_name("config_custom.txt")
REGNET_PORT = 3030
STARTUP_TIMEOUT = 30


def remaining_timeout(deadline):
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise TimeoutError("Regnet readiness deadline expired")
    return min(1.0, remaining)


def rpc_command(command, deadline):
    with socket.create_connection(
        ("127.0.0.1", REGNET_PORT), timeout=remaining_timeout(deadline)
    ) as connection:
        connection.settimeout(remaining_timeout(deadline))
        connections.send(connection, command)
        connection.settimeout(remaining_timeout(deadline))
        return connections.receive(connection)


def wait_for_regnet(process, readiness_token, timeout=STARTUP_TIMEOUT):
    deadline = monotonic() + timeout
    last_error = None
    while monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Regnet exited with status {process.returncode}")
        try:
            response = rpc_command("portget", deadline)
            runtime_config = rpc_command("api_getconfig", deadline)
            if (
                int(response["port"]) == REGNET_PORT
                and runtime_config.get("readiness_token") == readiness_token
            ):
                return
        except Exception as exc:
            last_error = exc
            sleep(min(0.25, max(0, deadline - monotonic())))
    raise RuntimeError(f"Regnet was not ready after {timeout}s: {last_error}")


def stop_regnet(process):
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def ensure_regnet_port_available():
    with socket.socket() as probe:
        probe.settimeout(0.25)
        if probe.connect_ex(("127.0.0.1", REGNET_PORT)) == 0:
            pytest.fail(f"Regnet port {REGNET_PORT} already has a listener")


def launch_regnet(command, regnet_dir):
    process = None
    node_output = None
    try:
        node_output = (regnet_dir / "node-output.log").open("w+")
        process = Popen(
            command,
            cwd=REPO_ROOT,
            stdout=node_output,
            stderr=STDOUT,
            text=True,
        )
        return process, node_output
    except BaseException:
        cleanup_regnet(process, node_output, None, regnet_dir)
        raise


def set_test_wallet_environment(wallet_file):
    previous = (
        "BISMUTH_TEST_WALLET" in os.environ,
        os.environ.get("BISMUTH_TEST_WALLET"),
    )
    os.environ["BISMUTH_TEST_WALLET"] = str(wallet_file)
    return previous


def restore_test_wallet_environment(previous):
    was_set, value = previous
    if was_set:
        os.environ["BISMUTH_TEST_WALLET"] = value
    else:
        os.environ.pop("BISMUTH_TEST_WALLET", None)


def cleanup_regnet(process, node_output, previous_wallet_environment, regnet_dir):
    try:
        if process is not None:
            stop_regnet(process)
    finally:
        try:
            if node_output is not None:
                node_output.close()
        finally:
            try:
                if previous_wallet_environment is not None:
                    restore_test_wallet_environment(previous_wallet_environment)
            finally:
                shutil.rmtree(regnet_dir, ignore_errors=True)


@pytest.fixture(scope="session")
def myserver(tmp_path_factory):
    ensure_regnet_port_available()
    regnet_dir = tmp_path_factory.mktemp("bismuth-regnet")
    process = None
    node_output = None
    previous_wallet_environment = None
    try:
        wallet_file = regnet_dir / "wallet.der"
        readiness_token = secrets.token_hex(16)
        command = [
            sys.executable,
            "node.py",
            "--config-custom",
            str(REGNET_CONFIG),
            "--regnet-dir",
            str(regnet_dir),
            "--wallet-file",
            str(wallet_file),
            "--bind",
            "127.0.0.1",
            "--readiness-token",
            readiness_token,
        ]
        previous_wallet_environment = (
            "BISMUTH_TEST_WALLET" in os.environ,
            os.environ.get("BISMUTH_TEST_WALLET"),
        )
        process, node_output = launch_regnet(command, regnet_dir)
        os.environ["BISMUTH_TEST_WALLET"] = str(wallet_file)
        try:
            wait_for_regnet(process, readiness_token)
        except Exception as exc:
            node_output.flush()
            node_output.seek(0)
            output = node_output.read()
            pytest.fail(f"{exc}\nCommand: {' '.join(command)}\nNode output:\n{output}")
        yield process
    finally:
        cleanup_regnet(
            process,
            node_output,
            previous_wallet_environment,
            regnet_dir,
        )
