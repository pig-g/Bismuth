# Lab 6: Difficulty Feedback

Watch how Bismuth's difficulty controller steers block time back toward a 60-second target, using a deterministic standalone simulation. This is a chemistry-free way to see the core idea without touching a live mainnet.

- **Time:** about 5 minutes
- **Guide:** read this page in GitHub or a Markdown editor
- **Runtime:** a read-only Python script from a local macOS or Linux Terminal

## The key idea

Bismuth targets roughly **one block every 60 seconds**. To keep that true as mining power changes, the node continuously adjusts the proof-of-work difficulty:

```text
blocks too fast  (block_time < 60s)  ->  difficulty falls  (mining gets easier)
blocks too slow  (block_time > 60s)  ->  difficulty rises  (mining gets harder)
```

The real rule lives in `node/difficulty.py`. It computes an average block time over a window, compares it to the 60-second target, and applies a small corrective move each block (plus an emergency drop if blocks stop entirely).

## Why simulate instead of watching the live chain

The educational regnet pins difficulty to a fixed value (`REGNET_DIFF = 16`) so that mining is immediate, deterministic, and cost-free. Because of that, a learner running a regnet node never sees difficulty actually move. This lab provides the missing view with a small arithmetic model of the same idea.

> **Safety:** this lab is pure arithmetic. It starts no node, opens no port, touches no database, holds no keys, and has no mainnet connection.

## 1. Run the simulator

From the repository root (the folder containing `node.py`, `tests`, and `labs`), after completing [Lab 0](../00-regnet-first-run/README.md) once so `.venv` exists:

```bash
.venv/bin/python ./labs/06-difficulty-simulation/simulate.py
```

## 2. Read the result

The output compares the controller's answer for different synthetic block times, starting from a difficulty of `100`:

```text
at target (60s)          -> difficulty 100.0000 (flat)
too fast (30s)           -> difficulty  99.4000 (down)
too slow (90s)           -> difficulty 100.6000 (up)
very slow (180s)         -> difficulty 102.4000 (up, stronger)
```

Verify all of these observations:

1. **At target (60s):** difficulty stays flat — the system is in balance.
2. **Too fast (30s):** difficulty falls. Mining becomes easier, which slows block production back toward 60s.
3. **Too slow (90s):** difficulty rises. Mining becomes harder, which speeds up block production back toward 60s.
4. **Very slow (180s):** difficulty rises even more — the larger the deviation, the stronger the corrective move.

## Reading the real code

Open `node/difficulty.py` and find the feedback controller around these lines:

```python
target = Decimal(60.00)                       # desired block time in seconds
Kd = 10                                       # feedback gain
block_time ...                               # measured average over a window
difficulty_new = difficulty_new - Kd * (block_time - block_time_prev)
diff_adjustment = (difficulty_new - diff_block_previous) / 720
```

The `- Kd * (block_time - block_time_prev)` term is the feedback that pulls block time back toward the average; the `/ 720` factor keeps each per-block change small. Two extra safeguards live here too:

- a **hard floor** so difficulty never drops below `50`;
- an **emergency drop** (`diff_drop_time = 180`) that cuts difficulty during a long block drought.

This lab models the *idea* with a small script rather than replaying the full windowed calculation, so the numbers differ from a mainnet node — but the direction and purpose match.

## Clean up

There is nothing to stop: the simulation is a short-lived read-only process and leaves no files, node, wallet, or port behind.

## What you learned

```text
Bismuth targets one block per 60 seconds
-> block time above target  => difficulty rises
-> block time below target  => difficulty falls
-> the controller steers block time back toward 60s
-> a floor and an emergency drop bound the range
-> regnet pins difficulty to 16, so the live node never shows this
```

This is the storage-free counterpart to the block structure you mapped in Lab 5: there you saw how a block is stored; here you see how the chain decides how hard the next block must be.
