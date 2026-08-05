from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON = REPO_ROOT / ".venv" / "bin" / "python"


def _run(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(PYTHON), str(script)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )


def _read_lab(name: str) -> str:
    return (REPO_ROOT / "labs" / name / "README.md").read_text()


def test_lab6_simulate_passes():
    result = _run(REPO_ROOT / "labs" / "06-difficulty-simulation" / "simulate.py")
    assert result.returncode == 0, result.stderr
    assert "difficulty" in result.stdout.lower()
    assert "too fast" in result.stdout and "too slow" in result.stdout


def test_lab6_guide_documents_direction_safety():
    guide = _read_lab("06-difficulty-simulation")
    assert "60" in guide
    assert "regnet pins difficulty" in guide or "REGNET_DIFF" in guide
    assert "no mainnet" in guide.lower() or "no node" in guide.lower()


def test_lab7_fork_demo_passes():
    result = _run(REPO_ROOT / "labs" / "07-fork-selection" / "fork_demo.py")
    assert result.returncode == 0, result.stderr
    assert "mainnet0020" in result.stdout
    assert "POW_FORK" in result.stdout or "Hard fork" in result.stdout


def test_lab7_guide_documents_fork_rules():
    guide = _read_lab("07-fork-selection")
    assert "POW_FORK" in guide and "REWARD_MAX" in guide
    assert "fail-safe" in guide.lower() or "assumes the fork passed" in guide


def test_lab8_tokens_demo_passes():
    result = _run(REPO_ROOT / "labs" / "08-tokens-no-vm" / "tokens_demo.py")
    assert result.returncode == 0, result.stderr
    assert "reindex balance check: OK" in result.stdout
    assert "840" in result.stdout and "60" in result.stdout and "100" in result.stdout


def test_lab8_guide_documents_token_model():
    guide = _read_lab("08-tokens-no-vm")
    assert "token:issue" in guide and "token:transfer" in guide
    assert "reindex" in guide.lower()
