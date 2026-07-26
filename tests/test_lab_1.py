import importlib.util
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

import pytest

from common import get_client


REPO_ROOT = Path(__file__).resolve().parents[1]
LAB_DIR = REPO_ROOT / "labs" / "01-test-bis-workflow"
WORKFLOW_PATH = LAB_DIR / "run.py"


def load_workflow_module():
    spec = importlib.util.spec_from_file_location("lab_1_workflow", WORKFLOW_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_workflow_transfers_test_bis_and_queries_confirmed_ledger(myserver):
    workflow = load_workflow_module()
    result = workflow.run_workflow(get_client())

    assert result["amount"] == "1.00000000"
    assert result["recipient_balance"] == "1.00000000"
    assert result["transaction"]["txid"] == result["txid"]
    assert result["transaction"]["recipient"] == result["recipient"]
    assert result["ledger_entry"]["signature"].startswith(result["txid"])
    assert result["block"]["block_height"] == result["transaction"]["blockheight"]
    assert any(
        transaction["txid"] == result["txid"]
        for transaction in result["block"]["transactions"]
    )


def test_runner_requires_an_owned_standalone_regnet():
    result = subprocess.run(
        [sys.executable, str(WORKFLOW_PATH)],
        cwd="/tmp",
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode != 0
    assert "use ./scripts/regnet start" in result.stderr


def test_lab_one_documents_the_exact_practical_workflow():
    readme = (LAB_DIR / "README.md").read_text()

    assert (LAB_DIR / "run.py").is_file()
    assert (LAB_DIR / "verify.sh").stat().st_mode & 0o111
    for required_text in (
        "10–15 minutes",
        "Do not use real BIS",
        "./scripts/regnet start",
        ".venv/bin/python ./labs/01-test-bis-workflow/run.py",
        "./scripts/regnet stop",
        "TEST BIS WORKFLOW PASS",
        "regtest_generate",
        "balancegetjson",
        "api_gettransaction",
        "api_getblockfromheight",
        "addlistlimjson",
    ):
        assert required_text in readme


def test_verifier_runs_owned_lifecycle_and_reports_cleanup(tmp_path):
    lifecycle_log = tmp_path / "lifecycle.log"
    fake_regnet = tmp_path / "regnet"
    fake_regnet.write_text(
        "#!/usr/bin/env sh\n"
        'echo "$1" >> "$LAB1_LIFECYCLE_LOG"\n'
        "exit 0\n"
    )
    fake_regnet.chmod(0o755)
    fake_workflow = tmp_path / "workflow"
    fake_workflow.write_text("#!/usr/bin/env sh\necho TEST BIS WORKFLOW PASS\n")
    fake_workflow.chmod(0o755)
    with socket.socket() as port_picker:
        port_picker.bind(("127.0.0.1", 0))
        test_port = port_picker.getsockname()[1]
    environment = os.environ.copy()
    environment.update(
        LAB1_REGNET=str(fake_regnet),
        LAB1_WORKFLOW=str(fake_workflow),
        LAB1_REGNET_PORT=str(test_port),
        LAB1_LIFECYCLE_LOG=str(lifecycle_log),
        LAB1_SCRIPT_INTERPRETER="/bin/sh",
        PYTHON=sys.executable,
    )

    result = subprocess.run(
        [str(LAB_DIR / "verify.sh")],
        cwd="/tmp",
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert lifecycle_log.read_text().splitlines() == ["start", "stop"]
    assert "TEST BIS WORKFLOW PASS" in result.stdout
    assert f"cleanup: port {test_port} is closed" in result.stdout
    assert result.stdout.rstrip().endswith("LAB 1 PASS")


@pytest.mark.parametrize(
    ("sent_signal", "expected_status"),
    (
        (signal.SIGHUP, 129),
        (signal.SIGINT, 130),
        (signal.SIGTERM, 143),
    ),
)
def test_verifier_preserves_signal_status_and_stops_regnet(
    tmp_path, sent_signal, expected_status
):
    lifecycle_log = tmp_path / "lifecycle.log"
    ready_file = tmp_path / "workflow.ready"
    fake_regnet = tmp_path / "regnet"
    fake_regnet.write_text(
        "#!/usr/bin/env sh\n"
        'echo "$1" >> "$LAB1_LIFECYCLE_LOG"\n'
        "exit 0\n"
    )
    fake_regnet.chmod(0o755)
    fake_workflow = tmp_path / "workflow"
    fake_workflow.write_text(
        "#!/usr/bin/env sh\n"
        'touch "$LAB1_READY_FILE"\n'
        "sleep 2\n"
        "echo TEST BIS WORKFLOW PASS\n"
    )
    fake_workflow.chmod(0o755)
    with socket.socket() as port_picker:
        port_picker.bind(("127.0.0.1", 0))
        test_port = port_picker.getsockname()[1]
    environment = os.environ.copy()
    environment.update(
        LAB1_REGNET=str(fake_regnet),
        LAB1_WORKFLOW=str(fake_workflow),
        LAB1_REGNET_PORT=str(test_port),
        LAB1_LIFECYCLE_LOG=str(lifecycle_log),
        LAB1_READY_FILE=str(ready_file),
        LAB1_SCRIPT_INTERPRETER="/bin/sh",
        PYTHON=sys.executable,
    )

    stdout_path = tmp_path / "stdout"
    stderr_path = tmp_path / "stderr"
    with stdout_path.open("w") as stdout_file, stderr_path.open("w") as stderr_file:
        process = subprocess.Popen(
            [str(LAB_DIR / "verify.sh")],
            cwd="/tmp",
            env=environment,
            stdout=stdout_file,
            stderr=stderr_file,
            text=True,
        )
        deadline = time.monotonic() + 5
        while not ready_file.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready_file.exists()
        interrupted_at = time.monotonic()
        process.send_signal(sent_signal)
        process.wait(timeout=10)
    stdout = stdout_path.read_text()
    stderr = stderr_path.read_text()

    assert process.returncode == expected_status, stdout + stderr
    assert time.monotonic() - interrupted_at < 1.5
    assert "LAB 1 PASS" not in stdout
    assert lifecycle_log.read_text().splitlines() == ["start", "stop"]


def test_verifier_interrupted_during_start_still_stops_regnet(tmp_path):
    lifecycle_log = tmp_path / "lifecycle.log"
    start_ready = tmp_path / "start.ready"
    fake_regnet = tmp_path / "regnet"
    fake_regnet.write_text(
        "#!/usr/bin/env sh\n"
        'echo "$1" >> "$LAB1_LIFECYCLE_LOG"\n'
        'if [ "$1" = start ]; then\n'
        '  touch "$LAB1_START_READY"\n'
        "  sleep 1\n"
        "fi\n"
        "exit 0\n"
    )
    fake_regnet.chmod(0o755)
    fake_workflow = tmp_path / "workflow"
    fake_workflow.write_text("#!/usr/bin/env sh\nexit 0\n")
    fake_workflow.chmod(0o755)
    with socket.socket() as port_picker:
        port_picker.bind(("127.0.0.1", 0))
        test_port = port_picker.getsockname()[1]
    environment = os.environ.copy()
    environment.update(
        LAB1_REGNET=str(fake_regnet),
        LAB1_WORKFLOW=str(fake_workflow),
        LAB1_REGNET_PORT=str(test_port),
        LAB1_LIFECYCLE_LOG=str(lifecycle_log),
        LAB1_START_READY=str(start_ready),
        LAB1_SCRIPT_INTERPRETER="/bin/sh",
        PYTHON=sys.executable,
    )

    process = subprocess.Popen(
        [str(LAB_DIR / "verify.sh")],
        cwd="/tmp",
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 5
    while not start_ready.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert start_ready.exists()
    process.send_signal(signal.SIGTERM)
    process.wait(timeout=10)

    assert process.returncode == 143
    assert lifecycle_log.read_text().splitlines() == ["start", "stop"]


def test_verifier_preserves_workflow_failure_and_stops_regnet(tmp_path):
    lifecycle_log = tmp_path / "lifecycle.log"
    fake_regnet = tmp_path / "regnet"
    fake_regnet.write_text(
        "#!/usr/bin/env sh\n"
        'echo "$1" >> "$LAB1_LIFECYCLE_LOG"\n'
        "exit 0\n"
    )
    fake_regnet.chmod(0o755)
    fake_workflow = tmp_path / "workflow"
    fake_workflow.write_text("#!/usr/bin/env sh\nexit 7\n")
    fake_workflow.chmod(0o755)
    with socket.socket() as port_picker:
        port_picker.bind(("127.0.0.1", 0))
        test_port = port_picker.getsockname()[1]
    environment = os.environ.copy()
    environment.update(
        LAB1_REGNET=str(fake_regnet),
        LAB1_WORKFLOW=str(fake_workflow),
        LAB1_REGNET_PORT=str(test_port),
        LAB1_LIFECYCLE_LOG=str(lifecycle_log),
        LAB1_SCRIPT_INTERPRETER="/bin/sh",
        PYTHON=sys.executable,
    )

    result = subprocess.run(
        [str(LAB_DIR / "verify.sh")],
        cwd="/tmp",
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert result.returncode == 7
    assert "LAB 1 PASS" not in result.stdout
    assert lifecycle_log.read_text().splitlines() == ["start", "stop"]


def test_verifier_refuses_preoccupied_port_without_starting_regnet(tmp_path):
    lifecycle_log = tmp_path / "lifecycle.log"
    fake_regnet = tmp_path / "regnet"
    fake_regnet.write_text(
        "#!/usr/bin/env sh\n"
        'echo "$1" >> "$LAB1_LIFECYCLE_LOG"\n'
        "exit 0\n"
    )
    fake_regnet.chmod(0o755)
    fake_workflow = tmp_path / "workflow"
    fake_workflow.write_text("#!/usr/bin/env sh\nexit 0\n")
    fake_workflow.chmod(0o755)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    test_port = listener.getsockname()[1]
    environment = os.environ.copy()
    environment.update(
        LAB1_REGNET=str(fake_regnet),
        LAB1_WORKFLOW=str(fake_workflow),
        LAB1_REGNET_PORT=str(test_port),
        LAB1_LIFECYCLE_LOG=str(lifecycle_log),
        LAB1_SCRIPT_INTERPRETER="/bin/sh",
        PYTHON=sys.executable,
    )

    try:
        result = subprocess.run(
            [str(LAB_DIR / "verify.sh")],
            cwd="/tmp",
            env=environment,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert listener.getsockname()[1] == test_port
    finally:
        listener.close()

    assert result.returncode != 0
    assert "already in use; refusing to start" in result.stderr
    assert not lifecycle_log.exists()


def test_verifier_reports_stop_failure_after_successful_workflow(tmp_path):
    lifecycle_log = tmp_path / "lifecycle.log"
    fake_regnet = tmp_path / "regnet"
    fake_regnet.write_text(
        "#!/usr/bin/env sh\n"
        'echo "$1" >> "$LAB1_LIFECYCLE_LOG"\n'
        'if [ "$1" = stop ]; then exit 8; fi\n'
        "exit 0\n"
    )
    fake_regnet.chmod(0o755)
    fake_workflow = tmp_path / "workflow"
    fake_workflow.write_text("#!/usr/bin/env sh\necho TEST BIS WORKFLOW PASS\n")
    fake_workflow.chmod(0o755)
    with socket.socket() as port_picker:
        port_picker.bind(("127.0.0.1", 0))
        test_port = port_picker.getsockname()[1]
    environment = os.environ.copy()
    environment.update(
        LAB1_REGNET=str(fake_regnet),
        LAB1_WORKFLOW=str(fake_workflow),
        LAB1_REGNET_PORT=str(test_port),
        LAB1_LIFECYCLE_LOG=str(lifecycle_log),
        LAB1_SCRIPT_INTERPRETER="/bin/sh",
        PYTHON=sys.executable,
    )

    result = subprocess.run(
        [str(LAB_DIR / "verify.sh")],
        cwd="/tmp",
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert result.returncode == 8
    assert "regnet stop failed" in result.stderr
    assert "LAB 1 PASS" not in result.stdout
    assert lifecycle_log.read_text().splitlines() == ["start", "stop", "stop"]
