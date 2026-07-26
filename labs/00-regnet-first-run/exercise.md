# Lab 0 Exercise: Diagnose One Cause Behind 26 Failures

Write your answers before opening `instructor.md`. Work from the repository root.
Do not connect to mainnet and do not substitute a real wallet.

## Incident evidence

The historical run launched:

```text
python3 node.py regnet2
```

After a ten-second wait, every integration test attempted `127.0.0.1:3030` and
failed with `ConnectionRefusedError`. Treat “26 failures” as a symptom count, not
as proof of 26 independent defects.

## Checkpoint 1 — Draw the boundary (10 minutes)

Inspect `tests/test_node.py`, `tests/common.py`, and `tests/conftest.py`.

1. Which process owns the ledger and listens for RPC?
2. Which component opens a client connection?
3. Complete this flow:

```text
pytest test -> __________ -> TCP port ______ -> __________
```

4. Why can one missing listener make unrelated transaction, mempool, ledger, and
   crypto-facing integration tests fail together?

## Checkpoint 2 — Compare the intended and effective startup (15 minutes)

Inspect `tests/config_custom.txt`, `node_cli.py`, and the command assembled in the
`myserver` fixture.

Record the intended values:

| Property | Expected regnet value |
|---|---|
| network version | |
| RPC port | |
| bind host | |
| data directory | |
| wallet path | |

Now compare the old positional launch with the current explicit launch. Answer:

1. What did the tests assume was listening on port `3030`?
2. If the node remained on its default path, which port would it select?
3. Is it more useful to debug the 26 test bodies first, or verify the shared
   process/network contract first? Why?

## Checkpoint 3 — Replace sleep with evidence (15 minutes)

Read `wait_for_regnet` and `rpc_command` in `tests/conftest.py`.

1. Why does “the process has not exited” not mean “the correct node is ready”?
2. What does the `portget` response prove?
3. What do `api_getconfig` and its random ownership token prove that an open TCP
   socket alone cannot?
4. Why is the timeout recomputed before connect, send, and receive?
5. Where is `node-output.log` surfaced when readiness fails, and why is that an
   actionable failure rather than a generic connection error?

## Checkpoint 4 — Run and verify cleanup (20–40 minutes)

Run the one-command verifier:

```bash
./labs/00-regnet-first-run/verify.sh
```

Capture these observations:

- focused Lab 0 acceptance tests pass;
- the live RPC checks report regnet port `3030`;
- the complete selected test path passes;
- the final output says port `3030` is closed;
- no temporary wallet, ledger, peer, or log file appears in the repository.

Then answer:

1. Which function performs process termination and escalates to kill if needed?
2. Which nested cleanup steps still run if stopping the process raises?
3. Why should the verifier fail before starting if port `3030` already has a
   listener?
4. What evidence would convince you that a failure is environmental rather than
   a test assertion failure?

## Exit ticket

In four sentences or fewer, explain:

1. the shared root cause of the historical 26 failures;
2. the difference between waiting and readiness;
3. the isolation boundary protecting mainnet state;
4. the final proof that the lab left no listener behind.
