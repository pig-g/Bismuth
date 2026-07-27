#!/usr/bin/env python3
"""Interactive, allowlisted CLI for an owned local Bismuth regnet."""

from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import secrets
import shlex
import signal
from subprocess import STDOUT, Popen
import sys
import tempfile

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bismuthclient.bismuthclient import BismuthClient
import regnet_control

SERVER = {f"{regnet_control.REGNET_HOST}:{regnet_control.REGNET_PORT}"}
ALLOWED_RPC = {
    "addlistlimjson",
    "api_getaddressinfo",
    "api_getbalance",
    "api_getblockfromhash",
    "api_getblockfromheight",
    "api_getconfig",
    "api_gettransaction",
    "api_mempool",
    "balancegetjson",
    "blocklastjson",
    "mpgetjson",
    "portget",
    "regtest_generate",
    "statusjson",
}
RPC_ARITY = {
    "addlistlimjson": (2, 2),
    "api_getaddressinfo": (1, 1),
    "api_getbalance": (2, 2),
    "api_getblockfromhash": (1, 1),
    "api_getblockfromheight": (1, 1),
    "api_getconfig": (0, 0),
    "api_gettransaction": (1, 2),
    "api_mempool": (0, 0),
    "balancegetjson": (1, 1),
    "blocklastjson": (0, 0),
    "mpgetjson": (0, 0),
    "portget": (0, 0),
    "regtest_generate": (0, 1),
    "statusjson": (0, 0),
}
HELP = """Commands:
  wallets                         show Alice and Bob addresses
  mine [count]                    mine 1-100 local blocks
  send <from> <to> <amount>       sign locally and send test BIS
  balance <wallet-or-address>     query balancegetjson
  tx <last-or-txid>               query api_gettransaction
  ledger <wallet-or-address> [n]  query addlistlimjson
  block <last-or-height>          show the latest or selected block
  block tx                        show the last sent transaction's block
  blocks [count]                  show recent block/transaction history
  blocks <start> <count>          show a block range (maximum 50)
  mempool                         query api_mempool
  rpc <allowed-command> [args]    execute an allowlisted Bismuth command
  help                            show this help
  quit                            stop and delete the local regnet

Aliases usable in commands: alice, bob, last.
Destructive, process-control, key-export, and remote-signing RPCs are blocked.
"""


class CLIError(RuntimeError):
    pass


class SessionInterrupted(BaseException):
    pass


def install_signal_handlers():
    def interrupt(signum, _frame):
        raise SessionInterrupted(f"interrupted by signal {signum}")

    for name in ("SIGHUP", "SIGINT", "SIGTERM"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), interrupt)


def create_client(wallet_file):
    return BismuthClient(servers_list=SERVER, wallet_file=str(wallet_file))


def generate_wallet(wallet_file):
    client = create_client(wallet_file)
    if not client.new_wallet(str(wallet_file)):
        raise RuntimeError("Could not create Bob's temporary wallet")
    client.load_wallet(str(wallet_file))
    if not client.address:
        raise RuntimeError("Bob's temporary wallet has no address")
    return client


def redact(value):
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if key == "readiness_token" else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def print_json(value):
    print(json.dumps(redact(value), indent=2, sort_keys=True, default=str))


def coerce(value):
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if value.startswith(("[", "{")):
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise CLIError(f"invalid JSON argument: {value}") from exc
    try:
        return int(value)
    except ValueError:
        return value


def is_identifier(value):
    return (
        isinstance(value, str)
        and len(value) == 56
        and all(character in "0123456789abcdef" for character in value)
    )


def validate_rpc_options(command, options):
    if command in {"api_getaddressinfo", "balancegetjson"}:
        if not is_identifier(options[0]):
            raise CLIError(f"{command} requires a 56-character lowercase hex address")
    elif command in {"api_getblockfromhash", "api_gettransaction"}:
        if not is_identifier(options[0]):
            raise CLIError(f"{command} requires a 56-character lowercase hex ID")
        if command == "api_gettransaction" and len(options) == 2:
            if type(options[1]) is not bool:
                raise CLIError("api_gettransaction format flag must be true or false")
    elif command == "api_getblockfromheight":
        if type(options[0]) is not int or options[0] < 1:
            raise CLIError("api_getblockfromheight requires a positive integer height")
    elif command == "addlistlimjson":
        if not is_identifier(options[0]):
            raise CLIError("addlistlimjson requires a 56-character lowercase hex address")
        if type(options[1]) is not int or not 1 <= options[1] <= 50:
            raise CLIError("addlistlimjson limit must be an integer from 1 to 50")
    elif command == "api_getbalance":
        addresses, minimum_confirmations = options
        if (
            not isinstance(addresses, list)
            or not 1 <= len(addresses) <= 50
            or not all(is_identifier(address) for address in addresses)
        ):
            raise CLIError(
                "api_getbalance requires a JSON list of 1-50 lowercase hex addresses"
            )
        if type(minimum_confirmations) is not int or minimum_confirmations < 0:
            raise CLIError("api_getbalance minimum confirmations must be nonnegative")


class RegnetCLI:
    def __init__(self, alice, bob):
        self.clients = {"alice": alice, "bob": bob}
        self.last_txid = None
        self.last_tx_confirmed = False

    @property
    def query_client(self):
        return self.clients["alice"]

    def address(self, value):
        return self.clients[value].address if value in self.clients else value

    def rpc(self, command, arguments):
        if command not in ALLOWED_RPC:
            raise CLIError(f"RPC {command} is not allowed")
        expanded = [
            self.last_txid if argument == "last" and self.last_txid else self.address(argument)
            for argument in arguments
        ]
        options = [coerce(argument) for argument in expanded]
        minimum, maximum = RPC_ARITY[command]
        if not minimum <= len(options) <= maximum:
            expected = str(minimum) if minimum == maximum else f"{minimum}-{maximum}"
            raise CLIError(f"RPC {command} expects {expected} argument(s)")
        validate_rpc_options(command, options)
        if command == "regtest_generate":
            count = options[0] if options else 1
            if type(count) is not int or not 1 <= count <= 100:
                raise CLIError("regtest_generate count must be an integer from 1 to 100")
            options = [count]
        print(f"RPC {command} {json.dumps(options)}")
        if command == "api_gettransaction":
            if not options:
                raise CLIError("api_gettransaction requires a transaction ID")
            raw = self.query_client.command(
                command="api_gettransaction", options=[options[0], False]
            )
            if raw is None:
                raise CLIError(
                    "transaction is not confirmed or does not exist; run mine 1 first"
                )
            if len(options) == 1:
                options.append(True)
        response = self.query_client.command(command=command, options=options)
        if command == "regtest_generate" and self.last_txid:
            self.last_tx_confirmed = True
        print_json(response)
        return response

    def print_block_history(self, arguments):
        if len(arguments) > 2:
            raise CLIError("usage: blocks [count] or blocks <start> <count>")
        latest = self.query_client.command(command="blocklastjson")
        latest_height = int(latest["block_height"])
        if len(arguments) == 2:
            start, count = map(coerce, arguments)
        else:
            count = coerce(arguments[0]) if arguments else 10
            start = max(1, latest_height - count + 1) if type(count) is int else 0
        if type(start) is not int or start < 1:
            raise CLIError("block history start must be a positive integer")
        if type(count) is not int or not 1 <= count <= 50:
            raise CLIError("block history count must be an integer from 1 to 50")
        end = min(latest_height, start + count - 1)
        print(f"BLOCK HISTORY {start}..{end} (tip {latest_height})")
        for height in range(start, end + 1):
            response = self.query_client.command(
                command="api_getblockfromheight", options=[height]
            )
            block = response.get(str(height), response.get(height))
            if not block:
                continue
            transactions = block.get("transactions", [])
            block_hash = str(block.get("block_hash", ""))
            print(
                f"height {height}  hash {block_hash[:16]}...  "
                f"transactions {len(transactions)}"
            )
            for transaction in transactions:
                txid = transaction.get("txid", "reward")
                sender = transaction.get("address", "mining")
                recipient = transaction.get("recipient", "")
                amount = transaction.get("amount", 0)
                reward = transaction.get("reward", 0)
                if reward:
                    print(f"  reward {reward} -> {recipient}")
                else:
                    print(
                        f"  tx {txid}  {sender} -> {recipient}  "
                        f"{amount} test BIS"
                    )

    def execute(self, line):
        try:
            words = shlex.split(line)
        except ValueError as exc:
            raise CLIError(str(exc)) from exc
        if not words:
            return True
        command, *arguments = words
        command = command.lower()

        if command in {"quit", "exit"}:
            return False
        if command == "help":
            print(HELP, end="")
            return True
        if command == "wallets":
            print(f"alice: {self.clients['alice'].address}")
            print(f"bob: {self.clients['bob'].address}")
            return True
        if command == "mine":
            if len(arguments) > 1:
                raise CLIError("usage: mine [count]")
            self.rpc("regtest_generate", arguments or ["1"])
            return True
        if command == "send":
            if len(arguments) != 3 or arguments[0] not in self.clients:
                raise CLIError("usage: send <alice|bob> <wallet-or-address> <amount>")
            sender_name, recipient_name, raw_amount = arguments
            try:
                amount = Decimal(raw_amount)
            except InvalidOperation as exc:
                raise CLIError("amount must be a decimal number") from exc
            if not Decimal("0") < amount <= Decimal("1000000"):
                raise CLIError("amount must be greater than 0 and at most 1000000")
            recipient = self.address(recipient_name)
            txid = self.clients[sender_name].send(
                recipient=recipient,
                amount=float(amount),
                operation="regnet-cli",
                data=f"{sender_name}-to-{recipient_name}",
            )
            if not isinstance(txid, str) or not txid:
                raise CLIError("transaction was rejected")
            self.last_txid = txid
            self.last_tx_confirmed = False
            print(
                f"{sender_name} -> {recipient_name}: {amount:.8f} test BIS\n"
                f"transaction: {txid}"
            )
            return True
        if command == "balance":
            if len(arguments) != 1:
                raise CLIError("usage: balance <wallet-or-address>")
            self.rpc("balancegetjson", [self.address(arguments[0])])
            return True
        if command == "tx":
            if len(arguments) != 1:
                raise CLIError("usage: tx <last-or-txid>")
            txid = self.last_txid if arguments[0] == "last" else arguments[0]
            if not txid:
                raise CLIError("there is no last transaction yet")
            if txid == self.last_txid and not self.last_tx_confirmed:
                raise CLIError("last transaction is unconfirmed; run mine 1 first")
            self.rpc("api_gettransaction", [txid, "true"])
            return True
        if command == "ledger":
            if not 1 <= len(arguments) <= 2:
                raise CLIError("usage: ledger <wallet-or-address> [limit]")
            self.rpc(
                "addlistlimjson",
                [self.address(arguments[0]), arguments[1] if len(arguments) == 2 else "10"],
            )
            return True
        if command == "block":
            if len(arguments) != 1:
                raise CLIError("usage: block <last|tx|height>")
            height = arguments[0]
            if height == "last":
                latest = self.query_client.command(command="blocklastjson")
                height = latest["block_height"]
            elif height == "tx":
                if not self.last_txid:
                    raise CLIError("there is no last sent transaction yet")
                if not self.last_tx_confirmed:
                    raise CLIError(
                        "last sent transaction is unconfirmed; run mine 1 first"
                    )
                transaction = self.query_client.command(
                    command="api_gettransaction", options=[self.last_txid, True]
                )
                height = transaction.get("blockheight")
                if height is None:
                    raise CLIError("last transaction is not confirmed; mine a block first")
            self.rpc("api_getblockfromheight", [str(height)])
            return True
        if command == "blocks":
            self.print_block_history(arguments)
            return True
        if command == "mempool":
            self.rpc("api_mempool", [])
            return True
        if command == "rpc":
            if not arguments:
                raise CLIError("usage: rpc <allowed-command> [arguments]")
            self.rpc(arguments[0], arguments[1:])
            return True
        raise CLIError(f"unknown command: {command}; use help")


def run_cli(alice_wallet, bob_wallet, process):
    cli = RegnetCLI(create_client(alice_wallet), generate_wallet(bob_wallet))
    print("BISMUTH REGNET CLI")
    print("Owned local node: 127.0.0.1:3030 (no mainnet, no real BIS)")
    print("Type help for commands. Type quit to stop and delete all session state.")
    while True:
        if process.poll() is not None:
            raise RuntimeError(f"owned regnet node exited with status {process.returncode}")
        try:
            line = input("regnet> ")
        except EOFError:
            print()
            return
        try:
            if not cli.execute(line):
                return
        except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
            print(f"error: {exc}")


def run_owned_node():
    if regnet_control.port_is_open():
        raise RuntimeError("Port 3030 is already occupied; refusing to touch its listener")
    process = None
    output = None
    with tempfile.TemporaryDirectory(prefix="bismuth-regnet-cli-") as temporary:
        runtime_dir = Path(temporary)
        alice_wallet = runtime_dir / "alice.der"
        bob_wallet = runtime_dir / "bob.der"
        readiness_token = secrets.token_hex(16)
        command = [
            sys.executable,
            str(REPO_ROOT / "node.py"),
            "--config-custom",
            str(regnet_control.REGNET_CONFIG),
            "--regnet-dir",
            str(runtime_dir),
            "--wallet-file",
            str(alice_wallet),
            "--bind",
            regnet_control.REGNET_HOST,
            "--readiness-token",
            readiness_token,
        ]
        try:
            output = (runtime_dir / "node-output.log").open("w")
            process = Popen(
                command,
                cwd=REPO_ROOT,
                stdout=output,
                stderr=STDOUT,
                text=True,
                start_new_session=True,
            )
            regnet_control.wait_for_regnet(process, readiness_token)
            run_cli(alice_wallet, bob_wallet, process)
        finally:
            try:
                if process is not None:
                    regnet_control.stop_regnet_process(process)
            finally:
                if output is not None:
                    output.close()
            if not regnet_control.wait_for_port_closed(5):
                raise RuntimeError("Regnet cleanup left port 3030 open")


def main():
    install_signal_handlers()
    try:
        run_owned_node()
    except (
        KeyError,
        OSError,
        RuntimeError,
        SessionInterrupted,
        TypeError,
        ValueError,
    ) as exc:
        print(f"regnet CLI: {exc}", file=sys.stderr)
        return 1
    print("Regnet stopped; temporary wallets and ledger removed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
