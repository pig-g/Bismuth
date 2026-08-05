import json
import os
from pathlib import Path
import signal

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def write_metadata(runtime_dir, pid=None, process_start_time=12345):
    runtime_dir.mkdir()
    runtime_stat = runtime_dir.stat()
    metadata = {
        "pid": pid or os.getpid(),
        "process_start_time": process_start_time,
        "readiness_token": "expected-token",
        "runtime_dir": str(runtime_dir),
        "runtime_device": runtime_stat.st_dev,
        "runtime_inode": runtime_stat.st_ino,
        "data_dir": str(runtime_dir / "data"),
        "wallet_file": str(runtime_dir / "data" / "wallet.der"),
        "log_file": str(runtime_dir / "node-output.log"),
        "command": ["python", "node.py"],
    }
    (runtime_dir / "metadata.json").write_text(json.dumps(metadata))
    return metadata


def record_recovery_identity(process, runtime_dir, process_start_time=12345):
    path = runtime_dir / "recovery.json"
    recovery = json.loads(path.read_text())
    recovery.update(
        pid=process.pid,
        process_start_time=process_start_time,
        state="ownership-recorded",
    )
    path.write_text(json.dumps(recovery))
    return recovery


def test_regnet_control_has_executable_cli_and_practical_commands():
    script = REPO_ROOT / "scripts" / "regnet"
    readme = REPO_ROOT / "labs" / "00-regnet-first-run" / "README.md"

    assert script.is_file()
    assert script.stat().st_mode & 0o111
    text = readme.read_text()
    for command in (
        "./scripts/regnet start",
        "./scripts/regnet status",
        "./scripts/regnet stop",
    ):
        assert command in text


def test_build_node_command_uses_explicit_isolation(tmp_path):
    import regnet_control

    runtime_dir = tmp_path / "bismuth-regnet-test"
    command = regnet_control.build_node_command(
        Path("/opt/python"), runtime_dir, "ownership-token"
    )

    assert command[0] == "/opt/python"
    assert command[1] == str(REPO_ROOT / "node.py")
    assert command[command.index("--config-custom") + 1] == str(
        REPO_ROOT / "tests" / "config_custom.txt"
    )
    assert command[command.index("--regnet-dir") + 1] == str(runtime_dir / "data")
    assert command[command.index("--wallet-file") + 1] == str(
        runtime_dir / "data" / "wallet.der"
    )
    assert command[command.index("--bind") + 1] == "127.0.0.1"
    assert command[command.index("--readiness-token") + 1] == "ownership-token"


def test_runtime_dir_rejects_repository_overlap_and_symlink(tmp_path):
    import regnet_control

    with pytest.raises(ValueError, match="outside the repository"):
        regnet_control.validate_runtime_dir(REPO_ROOT / "bismuth-regnet-test")

    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "bismuth-regnet-link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        regnet_control.validate_runtime_dir(link)


def test_rpc_command_bounds_protocol_receive_to_remaining_deadline(monkeypatch):
    import regnet_control

    operation_timeouts = []
    writes = []
    times = iter((9.0, 9.2, 9.4, 9.9))

    class FakeConnection:
        responses = iter((b"0000000004", b'"ok"'))

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def settimeout(self, timeout):
            operation_timeouts.append(timeout)

        def sendall(self, payload):
            writes.append(payload)

        def recv(self, _size):
            return next(self.responses)

    monkeypatch.setattr(regnet_control, "monotonic", lambda: next(times))
    monkeypatch.setattr(
        regnet_control.socket,
        "create_connection",
        lambda *_args, **_kwargs: FakeConnection(),
    )
    assert regnet_control.rpc_command("portget", deadline=10.0) == "ok"
    assert writes == [b"0000000009\"portget\""]
    assert operation_timeouts == pytest.approx([0.8, 0.6, 0.1])


def test_rpc_command_rejects_oversized_foreign_response(monkeypatch):
    import regnet_control

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def settimeout(self, _timeout):
            pass

        def sendall(self, _payload):
            pass

        def recv(self, _size):
            return b"9999999999"

    monkeypatch.setattr(regnet_control, "monotonic", lambda: 9.0)
    monkeypatch.setattr(
        regnet_control.socket,
        "create_connection",
        lambda *_args, **_kwargs: FakeConnection(),
    )

    with pytest.raises(RuntimeError, match="exceeds"):
        regnet_control.rpc_command("api_getconfig", deadline=10.0)


def test_start_refuses_an_occupied_port_without_creating_state(tmp_path, monkeypatch):
    import regnet_control

    runtime_dir = tmp_path / "bismuth-regnet-test"
    monkeypatch.setattr(regnet_control, "port_is_open", lambda: True)

    with pytest.raises(RuntimeError, match="3030"):
        regnet_control.start(runtime_dir=runtime_dir, python=Path("/opt/python"))

    assert not runtime_dir.exists()


def test_start_does_not_delete_a_concurrently_created_runtime(tmp_path, monkeypatch):
    import regnet_control

    runtime_dir = tmp_path / "bismuth-regnet-test"
    runtime_dir.mkdir()
    sentinel = runtime_dir / "foreign-state"
    sentinel.write_text("owned elsewhere")
    monkeypatch.setattr(regnet_control, "port_is_open", lambda: False)

    with pytest.raises(RuntimeError, match="already exists"):
        regnet_control.start(runtime_dir=runtime_dir, python=Path("/opt/python"))

    assert sentinel.read_text() == "owned elsewhere"


def test_status_and_stop_report_unowned_listener_without_metadata(
    tmp_path, monkeypatch
):
    import regnet_control

    runtime_dir = tmp_path / "bismuth-regnet-test"
    monkeypatch.setattr(regnet_control, "port_is_open", lambda: True)

    current = regnet_control.status(runtime_dir=runtime_dir)
    assert current.running is False
    assert current.message == "unowned listener on port 3030"
    with pytest.raises(RuntimeError, match="unowned listener"):
        regnet_control.stop(runtime_dir=runtime_dir)


def test_lifecycle_lock_prevents_runtime_generation_overlap(tmp_path, monkeypatch):
    import regnet_control

    runtime_dir = tmp_path / "bismuth-regnet-test"
    monkeypatch.setattr(regnet_control, "port_is_open", lambda: False)

    with regnet_control.runtime_lock(runtime_dir):
        for operation in (
            lambda: regnet_control.start(runtime_dir=runtime_dir),
            lambda: regnet_control.status(runtime_dir=runtime_dir),
            lambda: regnet_control.stop(runtime_dir=runtime_dir),
        ):
            with pytest.raises(RuntimeError, match="lifecycle command is in progress"):
                operation()

    lock_path = runtime_dir.parent / f".{runtime_dir.name}.lock"
    assert lock_path.stat().st_mode & 0o077 == 0
    assert regnet_control.status(runtime_dir=runtime_dir).message == "stopped"


def test_cleanup_fd_does_not_follow_runtime_path_replacement(tmp_path, monkeypatch):
    import regnet_control

    runtime_dir = tmp_path / "bismuth-regnet-test"
    write_metadata(runtime_dir)
    original_clear = regnet_control._clear_runtime_fd
    replaced = False

    def replace_generation_before_delete(directory_fd):
        nonlocal replaced
        if replaced:
            return original_clear(directory_fd)
        replaced = True
        runtime_dir.rename(tmp_path / "old-generation")
        runtime_dir.mkdir()
        (runtime_dir / "new-generation").write_text("preserve")
        original_clear(directory_fd)

    monkeypatch.setattr(regnet_control, "open_process_handle", lambda _pid: None)
    monkeypatch.setattr(regnet_control, "port_is_open", lambda: False)
    monkeypatch.setattr(
        regnet_control, "_clear_runtime_fd", replace_generation_before_delete
    )

    with pytest.raises(RuntimeError, match="runtime path changed"):
        regnet_control.stop(runtime_dir=runtime_dir)
    assert (runtime_dir / "new-generation").read_text() == "preserve"


def test_cleanup_refuses_replacement_before_runtime_fd_open(tmp_path, monkeypatch):
    import regnet_control

    runtime_dir = tmp_path / "bismuth-regnet-test"
    write_metadata(runtime_dir)

    def replace_generation(_pid):
        runtime_dir.rename(tmp_path / "old-generation")
        runtime_dir.mkdir()
        (runtime_dir / "new-generation").write_text("preserve")
        return None

    monkeypatch.setattr(regnet_control, "open_process_handle", replace_generation)
    monkeypatch.setattr(regnet_control, "port_is_open", lambda: False)

    with pytest.raises(RuntimeError, match="runtime generation changed"):
        regnet_control.stop(runtime_dir=runtime_dir)
    assert (runtime_dir / "new-generation").read_text() == "preserve"


def test_start_cleans_runtime_when_token_creation_is_interrupted(tmp_path, monkeypatch):
    import regnet_control

    runtime_dir = tmp_path / "bismuth-regnet-test"
    monkeypatch.setattr(regnet_control, "port_is_open", lambda: False)

    def interrupt_token(_length):
        raise KeyboardInterrupt()

    monkeypatch.setattr(regnet_control.secrets, "token_hex", interrupt_token)

    with pytest.raises(KeyboardInterrupt):
        regnet_control.start(runtime_dir=runtime_dir, python=Path("/opt/python"))

    assert not runtime_dir.exists()


def test_start_preserves_recovery_metadata_when_process_stop_raises(
    tmp_path, monkeypatch
):
    import regnet_control

    runtime_dir = tmp_path / "bismuth-regnet-test"

    class FakeProcess:
        pid = 4242
        returncode = None

        def poll(self):
            return None

    def fail_not_ready(*_args, **_kwargs):
        raise RuntimeError("not ready")

    def fail_to_stop(_process):
        raise RuntimeError("stop failed")

    monkeypatch.setattr(regnet_control, "port_is_open", lambda: False)
    monkeypatch.setattr(regnet_control, "Popen", lambda *args, **kwargs: FakeProcess())
    monkeypatch.setattr(
        regnet_control, "wait_for_recovery_identity", record_recovery_identity
    )
    monkeypatch.setattr(regnet_control, "wait_for_regnet", fail_not_ready)
    monkeypatch.setattr(regnet_control, "stop_regnet_process", fail_to_stop)

    with pytest.raises(RuntimeError, match="not ready"):
        regnet_control.start(runtime_dir=runtime_dir, python=Path("/opt/python"))

    assert runtime_dir.exists()
    assert (runtime_dir / "metadata.json").is_file()


def test_start_preserves_child_written_identity_when_metadata_and_stop_fail(
    tmp_path, monkeypatch
):
    import regnet_control

    runtime_dir = tmp_path / "bismuth-regnet-test"

    class FakeProcess:
        pid = 4242
        returncode = None

        def poll(self):
            return None

    def fail_metadata(_runtime_dir, _metadata):
        raise OSError("metadata write failed")

    def fail_stop(_process):
        raise RuntimeError("stop failed")

    monkeypatch.setattr(regnet_control, "port_is_open", lambda: False)
    monkeypatch.setattr(regnet_control, "Popen", lambda *args, **kwargs: FakeProcess())
    monkeypatch.setattr(
        regnet_control, "wait_for_recovery_identity", record_recovery_identity
    )
    monkeypatch.setattr(regnet_control, "_write_metadata", fail_metadata)
    monkeypatch.setattr(regnet_control, "stop_regnet_process", fail_stop)

    with pytest.raises(OSError, match="metadata write failed"):
        regnet_control.start(runtime_dir=runtime_dir, python=Path("/opt/python"))

    recovery = json.loads((runtime_dir / "recovery.json").read_text())
    assert recovery["pid"] == 4242
    assert recovery["command"][1] == str(REPO_ROOT / "node.py")
    assert recovery["process_start_time"] == 12345
    assert recovery["state"] == "ownership-recorded"
    assert not (runtime_dir / "metadata.json").exists()


def test_recovery_record_is_initialized_before_child_launch(tmp_path, monkeypatch):
    import regnet_control

    runtime_dir = tmp_path / "bismuth-regnet-test"
    launched = False

    def fail_recovery_write(_runtime_dir, _metadata):
        raise OSError("recovery write failed")

    def record_launch(*_args, **_kwargs):
        nonlocal launched
        launched = True
        raise AssertionError("child must not launch")

    monkeypatch.setattr(regnet_control, "port_is_open", lambda: False)
    monkeypatch.setattr(regnet_control, "_write_recovery_metadata", fail_recovery_write)
    monkeypatch.setattr(regnet_control, "Popen", record_launch)

    with pytest.raises(OSError, match="recovery write failed"):
        regnet_control.start(runtime_dir=runtime_dir, python=Path("/opt/python"))

    assert launched is False
    assert not runtime_dir.exists()


def test_start_status_stop_escalates_and_removes_isolated_state(tmp_path, monkeypatch):
    import regnet_control

    runtime_dir = tmp_path / "bismuth-regnet-test"
    events = []

    class FakeProcess:
        pid = 4242
        returncode = None

        def poll(self):
            return None

    monkeypatch.setattr(regnet_control, "port_is_open", lambda: False)
    monkeypatch.setattr(regnet_control, "Popen", lambda *args, **kwargs: FakeProcess())
    monkeypatch.setattr(
        regnet_control, "wait_for_recovery_identity", record_recovery_identity
    )
    monkeypatch.setattr(regnet_control, "wait_for_regnet", lambda *args, **kwargs: None)
    monkeypatch.setattr(regnet_control.secrets, "token_hex", lambda _length: "test-token")

    metadata = regnet_control.start(
        runtime_dir=runtime_dir,
        python=Path("/opt/python"),
    )

    assert metadata["pid"] == 4242
    assert metadata["process_start_time"] == 12345
    assert metadata["readiness_token"] == "test-token"
    assert json.loads((runtime_dir / "metadata.json").read_text()) == metadata

    monkeypatch.setattr(regnet_control, "pid_is_alive", lambda _pid: True)
    monkeypatch.setattr(regnet_control, "rpc_identity_matches", lambda _token: True)
    monkeypatch.setattr(regnet_control, "process_identity_matches", lambda _metadata: True)
    state = regnet_control.status(runtime_dir=runtime_dir)
    assert state.running is True
    assert state.message == "running"

    process_handle = os.open("/dev/null", os.O_RDONLY)
    monkeypatch.setattr(
        regnet_control, "open_process_handle", lambda _pid: process_handle
    )
    monkeypatch.setattr(
        regnet_control,
        "signal_process",
        lambda handle, sig: events.append((handle, sig)),
    )
    waits = iter((False, True))
    monkeypatch.setattr(
        regnet_control,
        "wait_for_process_exit",
        lambda _handle, _timeout: next(waits),
    )
    monkeypatch.setattr(regnet_control, "port_is_open", lambda: False)

    regnet_control.stop(runtime_dir=runtime_dir)

    assert events == [
        (process_handle, signal.SIGTERM),
        (process_handle, signal.SIGKILL),
    ]
    assert not runtime_dir.exists()


def test_process_identity_rejects_reused_pid_start_time(tmp_path, monkeypatch):
    import regnet_control

    runtime_dir = tmp_path / "bismuth-regnet-test"
    metadata = write_metadata(runtime_dir, process_start_time=12345)
    monkeypatch.setattr(regnet_control, "process_start_time", lambda _pid: 54321)

    assert regnet_control.process_identity_matches(metadata) is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("pid", 2**100),
        ("pid", 42.9),
        ("pid", float("inf")),
        ("process_start_time", True),
    ],
)
def test_metadata_rejects_invalid_numeric_identity(tmp_path, field, value):
    import regnet_control

    runtime_dir = tmp_path / "bismuth-regnet-test"
    metadata = write_metadata(runtime_dir)
    metadata[field] = value
    (runtime_dir / "metadata.json").write_text(json.dumps(metadata))

    with pytest.raises(RuntimeError, match="Invalid regnet metadata"):
        regnet_control.status(runtime_dir=runtime_dir)


def test_stop_refuses_foreign_or_reused_pid(tmp_path, monkeypatch):
    import regnet_control

    runtime_dir = tmp_path / "bismuth-regnet-test"
    write_metadata(runtime_dir)
    signals = []

    process_handle = os.open("/dev/null", os.O_RDONLY)
    monkeypatch.setattr(
        regnet_control, "open_process_handle", lambda _pid: process_handle
    )
    monkeypatch.setattr(regnet_control, "port_is_open", lambda: False)
    monkeypatch.setattr(regnet_control, "pid_is_alive", lambda _pid: True)
    monkeypatch.setattr(regnet_control, "rpc_identity_matches", lambda _token: True)
    monkeypatch.setattr(regnet_control, "process_identity_matches", lambda _metadata: False)
    monkeypatch.setattr(
        regnet_control,
        "signal_process",
        lambda handle, sig: signals.append((handle, sig)),
    )

    current = regnet_control.status(runtime_dir=runtime_dir)
    assert current.running is False
    assert current.message == "process or RPC ownership is unverified"

    with pytest.raises(RuntimeError, match="refusing"):
        regnet_control.stop(runtime_dir=runtime_dir)

    assert signals == []
    assert runtime_dir.exists()


def test_stop_refuses_foreign_listener_even_when_pid_command_matches(
    tmp_path, monkeypatch
):
    import regnet_control

    runtime_dir = tmp_path / "bismuth-regnet-test"
    write_metadata(runtime_dir)
    signals = []

    process_handle = os.open("/dev/null", os.O_RDONLY)
    monkeypatch.setattr(
        regnet_control, "open_process_handle", lambda _pid: process_handle
    )
    monkeypatch.setattr(regnet_control, "port_is_open", lambda: True)
    monkeypatch.setattr(regnet_control, "rpc_identity_matches", lambda _token: False)
    monkeypatch.setattr(regnet_control, "process_identity_matches", lambda _metadata: True)
    monkeypatch.setattr(
        regnet_control,
        "signal_process",
        lambda handle, sig: signals.append((handle, sig)),
    )

    with pytest.raises(RuntimeError, match="RPC ownership"):
        regnet_control.stop(runtime_dir=runtime_dir)

    assert signals == []
    assert runtime_dir.exists()


def test_stop_signals_stable_process_handle_instead_of_recorded_pid(
    tmp_path, monkeypatch
):
    import regnet_control

    runtime_dir = tmp_path / "bismuth-regnet-test"
    write_metadata(runtime_dir)
    signals = []
    closed = []
    real_close = os.close

    def record_close(handle):
        closed.append(handle)
        if handle != 77:
            real_close(handle)

    monkeypatch.setattr(regnet_control, "open_process_handle", lambda _pid: 77)
    monkeypatch.setattr(regnet_control, "port_is_open", lambda: False)
    monkeypatch.setattr(regnet_control, "process_identity_matches", lambda _metadata: True)
    monkeypatch.setattr(regnet_control, "wait_for_process_exit", lambda *_args: True)
    monkeypatch.setattr(
        regnet_control,
        "signal_process",
        lambda handle, sig: signals.append((handle, sig)),
    )
    monkeypatch.setattr(regnet_control.os, "close", record_close)

    regnet_control.stop(runtime_dir=runtime_dir)

    assert signals == [(77, signal.SIGTERM)]
    assert closed[0] == 77
    assert not runtime_dir.exists()


def test_stop_cleans_state_when_process_exits_before_sigkill(tmp_path, monkeypatch):
    import regnet_control

    runtime_dir = tmp_path / "bismuth-regnet-test"
    write_metadata(runtime_dir)
    process_handle = os.open("/dev/null", os.O_RDONLY)
    signals = []

    def signal_then_exit(handle, requested_signal):
        signals.append((handle, requested_signal))
        if requested_signal == signal.SIGKILL:
            raise ProcessLookupError()

    monkeypatch.setattr(
        regnet_control, "open_process_handle", lambda _pid: process_handle
    )
    monkeypatch.setattr(regnet_control, "port_is_open", lambda: False)
    monkeypatch.setattr(regnet_control, "process_identity_matches", lambda _metadata: True)
    monkeypatch.setattr(regnet_control, "wait_for_process_exit", lambda *_args: False)
    monkeypatch.setattr(regnet_control, "signal_process", signal_then_exit)

    assert regnet_control.stop(runtime_dir=runtime_dir) is True
    assert signals == [
        (process_handle, signal.SIGTERM),
        (process_handle, signal.SIGKILL),
    ]
    with pytest.raises(OSError):
        os.fstat(process_handle)
    assert not runtime_dir.exists()
