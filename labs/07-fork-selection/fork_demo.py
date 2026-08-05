#!/usr/bin/env python3
"""Lab 7: deterministic fork / chain-consensus rule verification.

Walks the learner through the Bismuth Fork class (node/fork.py): the hard-fork
height constants, the protocol-versions that stop being accepted at the fork,
and the post-fork reward check. It runs against deterministic in-memory
fixtures so the behaviour is reproducible and needs no live network.

Safety: read-only. No node, no port, no database on disk, no keys, no mainnet.
"""

import sys
from types import SimpleNamespace

REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fork import Fork  # noqa: E402


def make_node(version_allow):
    events = []
    logger = SimpleNamespace(app_log=SimpleNamespace(warning=events.append))
    return SimpleNamespace(
        version_allow=list(version_allow),
        last_block=1450000,
        logger=logger,
    ), events


class FakeDbRows:
    """Feeds fork.check_postfork_reward with a controllable row."""

    def __init__(self, reward):
        self.reward = reward  # None -> no row
        self.c = SimpleNamespace(fetchone=lambda: (self.reward,))
        self.h = SimpleNamespace(fetchone=lambda: (self.reward,))

    def execute_param(self, cursor, query, params):
        return None


class FakeDbRaise:
    """A db that raises, exercising fork.py's fail-safe 'assume valid' branch."""

    def __init__(self):
        self.c = SimpleNamespace(
            fetchone=self._boom,
        )
        self.h = SimpleNamespace(
            fetchone=self._boom,
        )

    def _boom(self):
        raise RuntimeError("synthetic db error")

    def execute_param(self, cursor, query, params):
        return None


def main():
    print("Lab 7: deterministic fork / consensus-rule verification")
    print("Using the real Fork class from node/fork.py against synthetic fixtures.\n")

    fork = Fork()
    print(f"Hard fork height (POW_FORK):      {fork.POW_FORK}")
    print(f"Fork look-ahead (FORK_AHEAD):     {fork.FORK_AHEAD}")
    print(f"Protocol versions removed:        {fork.versions_remove}")
    print(f"Reward cap enforced at fork:      {fork.REWARD_MAX}\n")

    # 1) version gating
    print("--- 1) protocol version gating at the fork height ---")
    node, events = make_node(["mainnet0023", "mainnet0020", "mainnet0019"])
    print(f"node accepts before: {list(node.version_allow)}")
    fork.limit_version(node)
    print(f"node accepts after:  {list(node.version_allow)}")
    print(f"removal log entries: {len(events)}")
    print()

    # 2) post-fork reward check below the reward cap
    print("--- 2) post-fork reward check ---")
    db_ok = FakeDbRows(5)
    passed = fork.check_postfork_reward(db_ok)
    print(f"reward=5 (< cap {fork.REWARD_MAX}):  passed={passed}  fork_passed={fork.PASSED}")

    db_over = FakeDbRows(10)
    fork.PASSED = False
    passed_over = fork.check_postfork_reward(db_over)
    print(f"reward=10 (>= cap {fork.REWARD_MAX}): passed={passed_over}  fork_passed={fork.PASSED}")

    # 3) fail-safe on a database error
    print("\n--- 3) fail-safe: db error assumes a valid fork ---")
    db_raise = FakeDbRaise()
    fork.PASSED = False
    passed_raise = fork.check_postfork_reward(db_raise)
    print(f"reward=db-error:            passed={passed_raise}  fork_passed={fork.PASSED}")

    print("\nObservation:")
    print("- at the fork height the node starts rejecting the removed protocol versions")
    print("- a post-fork reward below the cap confirms the fork; at/above the cap flags a problem")
    print("- on a database error fork.py assumes the fork passed (fail-safe, never freezes the chain)")


if __name__ == "__main__":
    main()
