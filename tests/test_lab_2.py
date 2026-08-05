from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[1]
LAB_DIR = REPO_ROOT / "labs" / "02-transaction-lifecycle"
README_PATH = LAB_DIR / "README.md"
CLI_PATH = REPO_ROOT / "labs" / "01-test-bis-workflow" / "cli.py"
EXPECTED_EXERCISE = [
    "wallets",
    "mine 1",
    "block last",
    "send alice bob 1",
    "mempool",
    "tx last",
    "block tx",
    "mine 1",
    "mempool",
    "tx last",
    "block tx",
    "blocks 10",
    "balance bob",
    "ledger bob 10",
    "rpc api_getconfig",
    "quit",
]


def exercise_commands(readme):
    match = re.search(
        r"<!-- exercise:start -->\n```text\n(.*?)\n```\n<!-- exercise:end -->",
        readme,
        re.DOTALL,
    )
    assert match is not None, "README must contain the marked learner exercise"
    return [line.strip() for line in match.group(1).splitlines() if line.strip()]


def test_lab_two_is_a_guide_for_the_existing_cli():
    readme = README_PATH.read_text()

    assert CLI_PATH.is_file()
    assert exercise_commands(readme) == EXPECTED_EXERCISE
    for required_text in (
        "Lab 2: Transaction Lifecycle and Block Explorer",
        ".venv/bin/python ./labs/01-test-bis-workflow/cli.py",
        "GitHub",
        "local macOS or Linux Terminal",
        "127.0.0.1:3030",
        "no real BIS",
        "mempool → unconfirmed transaction → confirmed block → ledger → balance",
        "last sent transaction is unconfirmed; run mine 1 first",
        "block last",
        "block tx",
        "same transaction ID",
        "Regnet stopped; temporary wallets and ledger removed.",
    ):
        assert required_text in readme


def test_lab_two_does_not_duplicate_the_cli_runtime():
    assert sorted(path.name for path in LAB_DIR.iterdir()) == ["README.md"]


def test_existing_cli_help_names_the_structured_mempool_rpc():
    cli_source = CLI_PATH.read_text()

    assert "mempool                         query mpgetjson" in cli_source
