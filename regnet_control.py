"""Safe lifecycle control for a standalone local Bismuth regnet."""

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import json
import os
from pathlib import Path
import select
import secrets
import signal
import socket
import stat
from subprocess import STDOUT, Popen, TimeoutExpired
import sys
import tempfile
from time import monotonic, sleep

REPO_ROOT = Path(__file__).resolve().parent
REGNET_CONFIG = REPO_ROOT / "tests" / "config_custom.txt"
REGNET_HOST = "127.0.0.1"
REGNET_PORT = 3030
STARTUP_TIMEOUT = 30
METADATA_NAME = "metadata.json"
RECOVERY_NAME = "recovery.json"
MAX_RPC_RESPONSE_BYTES = 1024 * 1024

RECOVERY_LAUNCHER = r"""
import json, os, pathlib, sys
recovery = pathlib.Path(sys.argv[1])
target = sys.argv[2:]
raw = pathlib.Path(f"/proc/{os.getpid()}/stat").read_text()
start_time = int(raw.rpartition(") ")[2].split()[19])
record = json.loads(recovery.read_text())
record.update(pid=os.getpid(), process_start_time=start_time, state="ownership-recorded")
temporary = recovery.with_name(f".{recovery.name}.child-{os.getpid()}")
temporary.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
temporary.chmod(0o600)
temporary.replace(recovery)
os.execv(target[0], target)
"""

@dataclass(frozen=True)
class RegnetStatus:
    running: bool
    message: str
    metadata: dict | None = None


def default_runtime_dir():
    uid = os.getuid() if hasattr(os, "getuid") else os.getpid()
    return Path(tempfile.gettempdir()) / f"bismuth-regnet-{uid}"


def validate_runtime_dir(runtime_dir):
    candidate = Path(runtime_dir).expanduser().absolute()
    if candidate.name in {"", ".", ".."} or not candidate.name.startswith(
        "bismuth-regnet-"
    ):
        raise ValueError("Regnet runtime directory must use a bismuth-regnet-* name")
    if candidate.is_symlink():
        raise ValueError("Regnet runtime directory must not be a symlink")
    resolved = candidate.resolve(strict=False)
    repository = REPO_ROOT.resolve()
    if (
        resolved == repository
        or resolved.is_relative_to(repository)
        or repository.is_relative_to(resolved)
    ):
        raise ValueError("Regnet runtime directory must be outside the repository")
    if candidate.exists() and not candidate.is_dir():
        raise ValueError("Regnet runtime path must be a directory")
    return resolved


@contextmanager
def runtime_lock(runtime_dir):
    lock_path = runtime_dir.parent / f".{runtime_dir.name}.lock"
    flags = os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW
    try:
        lock_fd = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise RuntimeError(f"Cannot open regnet lifecycle lock: {lock_path}") from exc
    try:
        lock_stat = os.fstat(lock_fd)
        if (
            not stat.S_ISREG(lock_stat.st_mode)
            or lock_stat.st_uid != os.getuid()
            or lock_stat.st_mode & 0o077
        ):
            raise RuntimeError("Regnet lifecycle lock is not private and user-owned")
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Another regnet lifecycle command is in progress") from exc
        yield
    finally:
        os.close(lock_fd)


def build_node_command(python, runtime_dir, readiness_token):
    runtime_dir = Path(runtime_dir)
    data_dir = runtime_dir / "data"
    return [
        str(python),
        str(REPO_ROOT / "node.py"),
        "--config-custom",
        str(REGNET_CONFIG),
        "--regnet-dir",
        str(data_dir),
        "--wallet-file",
        str(data_dir / "wallet.der"),
        "--bind",
        REGNET_HOST,
        "--readiness-token",
        readiness_token,
    ]


def build_launch_command(python, runtime_dir, command):
    return [
        str(python),
        "-c",
        RECOVERY_LAUNCHER,
        str(runtime_dir / RECOVERY_NAME),
        *command,
    ]


def wait_for_recovery_identity(process, runtime_dir, timeout=5):
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        try:
            recovery = json.loads((runtime_dir / RECOVERY_NAME).read_text())
        except (OSError, json.JSONDecodeError):
            recovery = {}
        if (
            recovery.get("pid") == process.pid
            and type(recovery.get("process_start_time")) is int
            and recovery["process_start_time"] > 0
            and recovery.get("state") == "ownership-recorded"
        ):
            return recovery
        if process.poll() is not None:
            raise RuntimeError("Regnet child exited before recording recovery identity")
        sleep(0.02)
    raise RuntimeError("Timed out waiting for regnet recovery identity")


def remaining_timeout(deadline):
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise TimeoutError("Regnet readiness deadline expired")
    return min(1.0, remaining)


def _send_json(connection, value, deadline):
    payload = json.dumps(value).encode("utf-8")
    header = str(len(payload)).encode("ascii").zfill(10)
    connection.settimeout(remaining_timeout(deadline))
    connection.sendall(header + payload)


def _recv_exact(connection, size, deadline):
    chunks = bytearray()
    while len(chunks) < size:
        connection.settimeout(remaining_timeout(deadline))
        chunk = connection.recv(size - len(chunks))
        if not chunk:
            raise RuntimeError("Regnet RPC closed before completing a response")
        chunks.extend(chunk)
    return bytes(chunks)


def _receive_json(connection, deadline):
    header = _recv_exact(connection, 10, deadline)
    if not header.isdigit():
        raise RuntimeError("Regnet RPC returned an invalid response header")
    size = int(header)
    if size > MAX_RPC_RESPONSE_BYTES:
        raise RuntimeError("Regnet RPC response exceeds the ownership-probe limit")
    try:
        return json.loads(_recv_exact(connection, size, deadline))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Regnet RPC returned invalid JSON") from exc


def rpc_command(command, deadline):
    with socket.create_connection(
        (REGNET_HOST, REGNET_PORT), timeout=remaining_timeout(deadline)
    ) as connection:
        _send_json(connection, command, deadline)
        return _receive_json(connection, deadline)


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


def port_is_open():
    with socket.socket() as probe:
        probe.settimeout(0.25)
        return probe.connect_ex((REGNET_HOST, REGNET_PORT)) == 0


def wait_for_port_closed(timeout):
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        if not port_is_open():
            return True
        sleep(0.1)
    return not port_is_open()


def stop_regnet_process(process):
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def choose_python():
    override = os.environ.get("PYTHON")
    if override:
        return Path(override)
    venv_python = REPO_ROOT / ".venv" / "bin" / "python"
    if venv_python.is_file():
        return venv_python
    return Path(sys.executable)


def _write_metadata(runtime_dir, metadata):
    destination = runtime_dir / METADATA_NAME
    temporary = runtime_dir / f".{METADATA_NAME}.tmp"
    temporary.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    temporary.chmod(0o600)
    temporary.replace(destination)


def _write_recovery_metadata(runtime_dir, metadata):
    destination = runtime_dir / RECOVERY_NAME
    temporary = runtime_dir / f".{RECOVERY_NAME}.tmp"
    temporary.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    temporary.chmod(0o600)
    temporary.replace(destination)


def _clear_runtime_fd(directory_fd):
    for name in os.listdir(directory_fd):
        entry_stat = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if stat.S_ISDIR(entry_stat.st_mode):
            child_fd = os.open(
                name,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=directory_fd,
            )
            try:
                opened_stat = os.fstat(child_fd)
                if (opened_stat.st_dev, opened_stat.st_ino) != (
                    entry_stat.st_dev,
                    entry_stat.st_ino,
                ):
                    raise RuntimeError("Runtime entry changed during cleanup")
                _clear_runtime_fd(child_fd)
            finally:
                os.close(child_fd)
            os.rmdir(name, dir_fd=directory_fd)
        else:
            os.unlink(name, dir_fd=directory_fd)


def remove_runtime(runtime_dir, expected_device, expected_inode):
    parent_fd = os.open(
        runtime_dir.parent,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
    )
    try:
        try:
            runtime_fd = os.open(
                runtime_dir.name,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=parent_fd,
            )
        except FileNotFoundError:
            return
        try:
            opened_stat = os.fstat(runtime_fd)
            if (opened_stat.st_dev, opened_stat.st_ino) != (
                expected_device,
                expected_inode,
            ):
                raise RuntimeError("Regnet runtime generation changed; refusing cleanup")
            _clear_runtime_fd(runtime_fd)
        finally:
            os.close(runtime_fd)
        current_stat = os.stat(
            runtime_dir.name, dir_fd=parent_fd, follow_symlinks=False
        )
        if (current_stat.st_dev, current_stat.st_ino) != (
            expected_device,
            expected_inode,
        ):
            raise RuntimeError("Regnet runtime path changed during cleanup")
        os.rmdir(runtime_dir.name, dir_fd=parent_fd)
    finally:
        os.close(parent_fd)


def runtime_identity(runtime_dir):
    runtime_stat = runtime_dir.stat(follow_symlinks=False)
    if not stat.S_ISDIR(runtime_stat.st_mode):
        raise RuntimeError("Regnet runtime generation is not a directory")
    return runtime_stat.st_dev, runtime_stat.st_ino


def process_start_time(pid):
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
        fields = stat.rpartition(") ")[2].split()
        return int(fields[19])
    except (OSError, IndexError, ValueError) as exc:
        raise RuntimeError("Cannot verify regnet process start identity") from exc


def process_command(pid):
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError as exc:
        raise RuntimeError("Cannot verify regnet process command identity") from exc
    return [os.fsdecode(argument) for argument in raw.rstrip(b"\0").split(b"\0")]


def load_metadata(runtime_dir):
    runtime_dir = validate_runtime_dir(runtime_dir)
    path = runtime_dir / METADATA_NAME
    if not path.is_file():
        return None
    try:
        metadata = json.loads(path.read_text())
        pid = metadata["pid"]
        recorded_start_time = metadata["process_start_time"]
        runtime_device = metadata["runtime_device"]
        runtime_inode = metadata["runtime_inode"]
        token = metadata["readiness_token"]
        recorded_runtime = Path(metadata["runtime_dir"]).resolve()
        data_dir = Path(metadata["data_dir"]).resolve()
        command = metadata["command"]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("Invalid regnet metadata; refusing process control") from exc
    if (
        type(pid) is not int
        or type(recorded_start_time) is not int
        or type(runtime_device) is not int
        or type(runtime_inode) is not int
        or not 1 < pid <= 2_147_483_647
        or not 0 < recorded_start_time <= 2**63 - 1
        or not 0 <= runtime_device <= 2**64 - 1
        or not 0 < runtime_inode <= 2**64 - 1
        or not isinstance(token, str)
        or not token
    ):
        raise RuntimeError("Invalid regnet metadata; refusing process control")
    if recorded_runtime != runtime_dir or not data_dir.is_relative_to(runtime_dir):
        raise RuntimeError("Regnet metadata paths do not match the runtime directory")
    if not isinstance(command, list) or not all(isinstance(item, str) for item in command):
        raise RuntimeError("Invalid regnet command metadata")
    metadata["pid"] = pid
    metadata["process_start_time"] = recorded_start_time
    metadata["runtime_device"] = runtime_device
    metadata["runtime_inode"] = runtime_inode
    return metadata


def pid_is_alive(pid):
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, OverflowError):
        return False
    except PermissionError:
        return True
    return True


def process_identity_matches(metadata):
    try:
        if process_start_time(metadata["pid"]) != metadata["process_start_time"]:
            return False
        return process_command(metadata["pid"]) == metadata["command"]
    except RuntimeError:
        return False


def rpc_identity_matches(readiness_token):
    deadline = monotonic() + 2
    try:
        response = rpc_command("portget", deadline)
        runtime_config = rpc_command("api_getconfig", deadline)
        return (
            int(response["port"]) == REGNET_PORT
            and runtime_config.get("readiness_token") == readiness_token
        )
    except Exception:
        return False


def open_process_handle(pid):
    if not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal"):
        raise RuntimeError(
            "Safe standalone regnet stop requires Linux pidfd support"
        )
    try:
        return os.pidfd_open(pid)
    except ProcessLookupError:
        return None


def signal_process(process_handle, requested_signal):
    signal.pidfd_send_signal(process_handle, requested_signal)


def wait_for_process_exit(process_handle, timeout):
    poller = select.poll()
    poller.register(process_handle, select.POLLIN)
    return bool(poller.poll(max(0, int(timeout * 1000))))


def start(runtime_dir=None, python=None):
    runtime_dir = validate_runtime_dir(runtime_dir or default_runtime_dir())
    with runtime_lock(runtime_dir):
        return _start_locked(runtime_dir, python)


def _start_locked(runtime_dir, python=None):
    if port_is_open():
        raise RuntimeError(f"Regnet port {REGNET_PORT} already has a listener")
    try:
        runtime_dir.mkdir(mode=0o700, parents=True)
    except FileExistsError:
        raise RuntimeError(
            f"Regnet runtime already exists at {runtime_dir}; run stop or inspect it"
        )
    runtime_device, runtime_inode = runtime_identity(runtime_dir)
    process = None
    output = None
    try:
        data_dir = runtime_dir / "data"
        data_dir.mkdir(mode=0o700)
        log_file = runtime_dir / "node-output.log"
        readiness_token = secrets.token_hex(16)
        python = Path(python) if python is not None else choose_python()
        command = build_node_command(python, runtime_dir, readiness_token)
        recovery_metadata = {
            "pid": None,
            "process_start_time": None,
            "readiness_token": readiness_token,
            "runtime_dir": str(runtime_dir),
            "runtime_device": runtime_device,
            "runtime_inode": runtime_inode,
            "data_dir": str(data_dir),
            "wallet_file": str(data_dir / "wallet.der"),
            "log_file": str(log_file),
            "command": command,
            "state": "launch-pending",
        }
        _write_recovery_metadata(runtime_dir, recovery_metadata)
        output = log_file.open("w")
        process = Popen(
            build_launch_command(python, runtime_dir, command),
            cwd=REPO_ROOT,
            stdout=output,
            stderr=STDOUT,
            text=True,
            start_new_session=True,
        )
        recovery_metadata = wait_for_recovery_identity(process, runtime_dir)
        recorded_start_time = recovery_metadata["process_start_time"]
        metadata = {
            "pid": process.pid,
            "process_start_time": recorded_start_time,
            "readiness_token": readiness_token,
            "runtime_dir": str(runtime_dir),
            "runtime_device": runtime_device,
            "runtime_inode": runtime_inode,
            "data_dir": str(data_dir),
            "wallet_file": str(data_dir / "wallet.der"),
            "log_file": str(log_file),
            "command": command,
        }
        _write_metadata(runtime_dir, metadata)
        (runtime_dir / RECOVERY_NAME).unlink()
        wait_for_regnet(process, readiness_token)
        return metadata
    except BaseException as original_error:
        cleanup_errors = []
        should_remove_runtime = process is None
        try:
            if process is not None:
                stop_regnet_process(process)
                should_remove_runtime = True
        except BaseException as cleanup_error:
            cleanup_errors.append(cleanup_error)
        try:
            if output is not None and not output.closed:
                output.close()
        except BaseException as cleanup_error:
            cleanup_errors.append(cleanup_error)
        if should_remove_runtime:
            try:
                remove_runtime(runtime_dir, runtime_device, runtime_inode)
            except BaseException as cleanup_error:
                cleanup_errors.append(cleanup_error)
        for cleanup_error in cleanup_errors:
            original_error.add_note(f"Cleanup also failed: {cleanup_error}")
        raise
    finally:
        if output is not None and not output.closed:
            output.close()


def status(runtime_dir=None):
    runtime_dir = validate_runtime_dir(runtime_dir or default_runtime_dir())
    with runtime_lock(runtime_dir):
        return _status_locked(runtime_dir)


def _status_locked(runtime_dir):
    metadata = load_metadata(runtime_dir)
    if metadata is None:
        if runtime_dir.exists():
            return RegnetStatus(False, "runtime exists without ownership metadata")
        if port_is_open():
            return RegnetStatus(False, "unowned listener on port 3030")
        return RegnetStatus(False, "stopped")
    alive = pid_is_alive(metadata["pid"])
    owned_rpc = rpc_identity_matches(metadata["readiness_token"])
    owned_process = alive and process_identity_matches(metadata)
    if owned_process and owned_rpc:
        return RegnetStatus(True, "running", metadata)
    if alive:
        return RegnetStatus(False, "process or RPC ownership is unverified", metadata)
    if port_is_open():
        return RegnetStatus(False, "stale metadata; port 3030 is owned by another process", metadata)
    return RegnetStatus(False, "stale metadata; recorded process is not running", metadata)


def stop(runtime_dir=None):
    runtime_dir = validate_runtime_dir(runtime_dir or default_runtime_dir())
    with runtime_lock(runtime_dir):
        return _stop_locked(runtime_dir)


def _stop_locked(runtime_dir):
    metadata = load_metadata(runtime_dir)
    if metadata is None:
        if runtime_dir.exists():
            raise RuntimeError("Regnet runtime exists without ownership metadata; refusing")
        if port_is_open():
            raise RuntimeError("Port 3030 has an unowned listener; refusing")
        return False
    pid = metadata["pid"]
    process_handle = open_process_handle(pid)
    if process_handle is None:
        if port_is_open():
            raise RuntimeError("Recorded process is gone but port 3030 is occupied; refusing")
        remove_runtime(
            runtime_dir, metadata["runtime_device"], metadata["runtime_inode"]
        )
        return False
    try:
        if port_is_open() and not rpc_identity_matches(metadata["readiness_token"]):
            raise RuntimeError("Port 3030 RPC ownership does not match; refusing to signal")
        if not process_identity_matches(metadata):
            raise RuntimeError("Process identity does not match regnet metadata; refusing")

        try:
            signal_process(process_handle, signal.SIGTERM)
        except ProcessLookupError:
            pass
        if not wait_for_process_exit(process_handle, 10):
            try:
                signal_process(process_handle, signal.SIGKILL)
            except ProcessLookupError:
                pass
            else:
                if not wait_for_process_exit(process_handle, 5):
                    raise RuntimeError("Regnet process survived SIGKILL")
    finally:
        os.close(process_handle)
    if not wait_for_port_closed(5):
        raise RuntimeError("Regnet process stopped but port 3030 still has a listener")
    remove_runtime(runtime_dir, metadata["runtime_device"], metadata["runtime_inode"])
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description="Control an isolated local Bismuth regnet")
    parser.add_argument("action", choices=("start", "status", "stop"))
    args = parser.parse_args(argv)
    try:
        if args.action == "start":
            metadata = start()
            print(f"Regnet running on {REGNET_HOST}:{REGNET_PORT}")
            print(f"Wallet: {metadata['wallet_file']}")
            print(f"Log: {metadata['log_file']}")
            return 0
        if args.action == "status":
            current = status()
            print(f"Regnet {current.message}")
            if current.metadata is not None:
                print(f"Runtime: {current.metadata['runtime_dir']}")
            return 0 if current.running else 1
        stopped = stop()
        print("Regnet stopped" if stopped else "Regnet was not running")
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"regnet: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
