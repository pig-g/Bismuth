from decimal import Decimal
import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LAB_DIR = REPO_ROOT / "labs" / "mainnet-interaction"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "mainnet_rpc", str(LAB_DIR / "mainnet_rpc.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeClient:
    """Client stand-in that records calls instead of touching the network."""

    def __init__(self):
        self.command_calls = []
        self.send_calls = []
        self.respond = {}
        self.send_result = "TxId1234567890+/".ljust(56, "A")
        self.address = "a" * 56

    def command(self, command, options=None):
        self.command_calls.append((command, list(options or [])))
        return self.respond.get(command)

    def send(self, recipient, amount, operation="", data=""):
        self.send_calls.append((recipient, amount, operation, data))
        return self.send_result


def test_warning_present():
    m = load_module()
    assert "REAL BISMUTH MAINNET" in m.MAINNET_WARNING
    assert "never sent to any node" in m.MAINNET_WARNING


def test_read_allowlist_accepts_only_safe_commands():
    m = load_module()
    client = FakeClient()
    client.respond["statusjson"] = {"block_height": 4914895}
    rpc = m.MainnetRPC(client)
    assert rpc.observe("statusjson") == {"block_height": 4914895}
    assert client.command_calls[-1] == ("statusjson", [])


def test_read_allowlist_rejects_write_command():
    m = load_module()
    rpc = m.MainnetRPC(FakeClient())
    try:
        rpc.observe("mpinsert", ["tx"])
    except m.MainnetError as exc:
        assert "not a read-only allowlisted" in str(exc)
    else:
        raise AssertionError("mpinsert should be rejected as read")


def test_blocked_send_commands_refused():
    m = load_module()
    rpc = m.MainnetRPC(FakeClient())
    for bad in ("txsend", "keygen", "api_clearmempool", "regtest_generate"):
        try:
            rpc.reject_if_blocked_send(bad)
        except m.MainnetError as exc:
            assert "blocked" in str(exc)
        else:
            raise AssertionError(f"{bad} should be blocked")


def test_block_height_parses():
    m = load_module()
    client = FakeClient()
    client.respond["blocklastjson"] = {"block_height": 4914895}
    rpc = m.MainnetRPC(client)
    assert rpc.block_height() == 4914895


def test_send_requires_confirmation():
    m = load_module()
    rpc = m.MainnetRPC(FakeClient())
    try:
        rpc.sign_and_send("b" * 56, Decimal("0.01"), confirm=False)
    except m.MainnetError as exc:
        assert "not confirmed" in str(exc)
    else:
        raise AssertionError("unconfirmed send must fail")


def test_send_enforces_small_trial_amount():
    m = load_module()
    rpc = m.MainnetRPC(FakeClient())
    try:
        rpc.sign_and_send("b" * 56, Decimal("5.0"), confirm=True)
    except m.MainnetError as exc:
        assert "small trial limit" in str(exc)
    else:
        raise AssertionError("large send must fail")


def test_send_confirmed_local_sign_path_used():
    m = load_module()
    client = FakeClient()
    rpc = m.MainnetRPC(client)
    txid = rpc.sign_and_send(
        "b" * 56, Decimal("0.01"), operation="mainnet-lab", data="hello",
        confirm=True,
    )
    assert txid == client.send_result
    recipient, amount, operation, data = client.send_calls[-1]
    assert recipient == "b" * 56
    assert amount == float(Decimal("0.01"))
    assert operation == "mainnet-lab" and data == "hello"


def test_parse_send_args():
    m = load_module()
    recipient, amount, operation, data = m.parse_send_args(
        "send bbb 0.01 mainnet-lab hello"
    )
    assert recipient == "bbb"
    assert amount == Decimal("0.01")
    assert operation == "mainnet-lab" and data == "hello"


def test_parse_send_args_rejects_oversize():
    m = load_module()
    try:
        m.parse_send_args("send bbb 50.0")
    except m.MainnetError as exc:
        assert "limit" in str(exc)
    else:
        raise AssertionError("oversize send args must fail")
