import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time


REPO_ROOT = Path(__file__).resolve().parents[1]
LAB_DIR = REPO_ROOT / "labs" / "00-regnet-first-run"


def test_lab_zero_has_complete_runnable_package():
    expected_files = {
        "README.md",
        "exercise.md",
        "instructor.md",
        "verify.sh",
    }

    assert expected_files <= {path.name for path in LAB_DIR.iterdir()}
    assert (LAB_DIR / "verify.sh").stat().st_mode & 0o111


def test_student_readme_defines_safe_bounded_learning_contract():
    readme = (LAB_DIR / "README.md").read_text()

    assert "60–90 minutes" in readme
    assert "Do not use real BIS" in readme
    assert "./labs/00-regnet-first-run/verify.sh" in readme
    for required_concept in (
        "Core node",
        "BismuthClient",
        "5658",
        "3030",
        "RPC readiness",
        "temporary data directory",
        "127.0.0.1",
    ):
        assert required_concept in readme


def test_exercise_and_instructor_cover_the_shared_failure_diagnosis():
    exercise = (LAB_DIR / "exercise.md").read_text()
    instructor = (LAB_DIR / "instructor.md").read_text()

    for checkpoint in (
        "Checkpoint 1",
        "Checkpoint 2",
        "Checkpoint 3",
        "Checkpoint 4",
        "ConnectionRefusedError",
        "portget",
        "api_getconfig",
        "node-output.log",
    ):
        assert checkpoint in exercise

    for answer in (
        "Shared root cause",
        "python3 node.py regnet2",
        "mainnet0022",
        "5658",
        "3030",
        "readiness_token",
        "fixed sleep",
        "cleanup",
    ):
        assert answer in instructor


def test_verifier_runs_the_regnet_runner_and_reports_cleanup(tmp_path):
    fake_runner = tmp_path / "regnet-runner.sh"
    fake_runner.write_text("#!/usr/bin/env sh\necho RUNNER_CALLED\n")
    fake_runner.chmod(0o755)
    with socket.socket() as port_picker:
        port_picker.bind(("127.0.0.1", 0))
        test_port = port_picker.getsockname()[1]
    environment = os.environ.copy()
    environment.update(
        PYTHON=sys.executable,
        LAB0_REGNET_RUNNER=str(fake_runner),
        LAB0_REGNET_PORT=str(test_port),
    )

    result = subprocess.run(
        [str(LAB_DIR / "verify.sh")],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "RUNNER_CALLED" in result.stdout
    assert f"port {test_port} is closed" in result.stdout
    assert result.stdout.rstrip().endswith("LAB 0 PASS")


def test_verifier_refuses_to_start_when_regnet_port_is_owned(tmp_path):
    runner_marker = tmp_path / "runner-called"
    fake_runner = tmp_path / "regnet-runner.sh"
    fake_runner.write_text(f"#!/usr/bin/env sh\ntouch '{runner_marker}'\n")
    environment = os.environ.copy()

    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        test_port = listener.getsockname()[1]
        environment.update(
            PYTHON=sys.executable,
            LAB0_REGNET_RUNNER=str(fake_runner),
            LAB0_REGNET_PORT=str(test_port),
        )
        result = subprocess.run(
            [str(LAB_DIR / "verify.sh")],
            cwd=REPO_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=15,
        )

    assert result.returncode != 0
    assert f"port {test_port} is already in use" in result.stderr
    assert not runner_marker.exists()


def test_verifier_checks_cleanup_after_runner_failure(tmp_path):
    fake_runner = tmp_path / "regnet-runner.sh"
    fake_runner.write_text("#!/usr/bin/env sh\nexit 7\n")
    with socket.socket() as port_picker:
        port_picker.bind(("127.0.0.1", 0))
        test_port = port_picker.getsockname()[1]
    environment = os.environ.copy()
    environment.update(
        PYTHON=sys.executable,
        LAB0_REGNET_RUNNER=str(fake_runner),
        LAB0_REGNET_PORT=str(test_port),
    )

    result = subprocess.run(
        [str(LAB_DIR / "verify.sh")],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert result.returncode == 7
    assert f"cleanup: port {test_port} is closed" in result.stdout
    assert "LAB 0 PASS" not in result.stdout


def test_verifier_reports_listener_leaked_by_failing_runner(tmp_path):
    leak_server = tmp_path / "leak_server.py"
    leak_server.write_text(
        "import socket, sys, time\n"
        "listener = socket.socket()\n"
        "listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)\n"
        "listener.bind(('127.0.0.1', int(sys.argv[1])))\n"
        "listener.listen()\n"
        "open(sys.argv[2], 'w').write('ready')\n"
        "time.sleep(30)\n"
    )
    ready_file = tmp_path / "listener-ready"
    pid_file = tmp_path / "listener-pid"
    fake_runner = tmp_path / "regnet-runner.sh"
    fake_runner.write_text(
        "#!/usr/bin/env sh\n"
        '"$PYTHON" "$LAB0_LEAK_SERVER" "$LAB0_REGNET_PORT" '
        '"$LAB0_READY_FILE" >/dev/null 2>&1 &\n'
        'echo $! > "$LAB0_PID_FILE"\n'
        "attempt=0\n"
        'while [ ! -f "$LAB0_READY_FILE" ]; do\n'
        "    attempt=$((attempt + 1))\n"
        '    [ "$attempt" -lt 100 ] || exit 10\n'
        "    sleep 0.02\n"
        "done\n"
        "exit 9\n"
    )
    with socket.socket() as port_picker:
        port_picker.bind(("127.0.0.1", 0))
        test_port = port_picker.getsockname()[1]
    environment = os.environ.copy()
    environment.update(
        PYTHON=sys.executable,
        LAB0_REGNET_RUNNER=str(fake_runner),
        LAB0_REGNET_PORT=str(test_port),
        LAB0_LEAK_SERVER=str(leak_server),
        LAB0_READY_FILE=str(ready_file),
        LAB0_PID_FILE=str(pid_file),
    )

    try:
        result = subprocess.run(
            [str(LAB_DIR / "verify.sh")],
            cwd=REPO_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=15,
        )
    finally:
        listener_closed = False
        if pid_file.exists():
            listener_pid = int(pid_file.read_text())
            try:
                os.kill(listener_pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with socket.socket() as probe:
                if probe.connect_ex(("127.0.0.1", test_port)) != 0:
                    listener_closed = True
                    break
            time.sleep(0.02)
        if not listener_closed and pid_file.exists():
            try:
                os.kill(listener_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                with socket.socket() as probe:
                    if probe.connect_ex(("127.0.0.1", test_port)) != 0:
                        listener_closed = True
                        break
                time.sleep(0.02)
        assert listener_closed, f"test teardown leaked listener on port {test_port}"

    assert result.returncode != 0
    assert f"cleanup failed: port {test_port} still has a listener" in result.stderr
    assert "LAB 0 PASS" not in result.stdout
