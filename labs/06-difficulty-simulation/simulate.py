#!/usr/bin/env python3
"""Lab 6: deterministic difficulty feedback simulation.

A standalone, read-only, purely-arithmetic model of the Bismuth difficulty
controller. Bismuth adjusts difficulty once per block using an EMA-influenced
feedback rule with a 60-second target block time; regnet pins difficulty to 16
so the live chain never shows this reaction. This sim lets a learner watch the
controller steer block time back toward the target.

NOTE: this is a simplified, self-contained teaching model of the idea, not a
verbatim re-run of node/difficulty.py. It isolates the one observation the lab
wants: block time deviation -> corrective difficulty move.

Safety: pure Decimal arithmetic only. No node, no port, no database, no keys.
"""

from decimal import Decimal, ROUND_HALF_UP

TARGET = Decimal("60.0")   # desired seconds per block
FLOOR = Decimal("50.0")    # difficulty floor, same spirit as difficulty.py


def quantize_ten(value):
    return value.quantize(Decimal("0.0000000000"), rounding=ROUND_HALF_UP)


def step(prev_difficulty, block_time, gain=Decimal("0.02")):
    """One corrective controller step.

    If blocks are slower than target (block_time > 60s) the controller makes
    mining harder (raises difficulty); if faster, it eases (lowers it). The
    magnitude is proportional to the deviation from target.
    """
    deviation = TARGET - block_time          # positive when blocks are too fast
    adjustment = gain * deviation
    new_difficulty = quantize_ten(prev_difficulty - adjustment)  # -adj => too-fast lowers diff
    if new_difficulty < FLOOR:
        new_difficulty = FLOOR
    return new_difficulty, adjustment


def main():
    print("Lab 6: deterministic difficulty feedback simulation")
    print("A simplified teaching model of the Bismuth difficulty controller.\n")
    print(f"Target block time: {float(TARGET):g}s | difficulty floor {float(FLOOR):g}s\n")

    cases = [
        ("at target (60s)",        "60.0"),
        ("too fast (30s)",         "30.0"),
        ("too slow (90s)",         "90.0"),
        ("very slow (180s)",       "180.0"),
    ]
    prev = Decimal("100.0000000000")
    print(f"starting difficulty: {prev}\n")
    for name, block_time_str in cases:
        block_time = Decimal(block_time_str)
        new_diff, adjustment = step(prev, block_time)
        direction = "up" if new_diff > prev else ("down" if new_diff < prev else "flat")
        print(f"{name:24s} block_time={float(block_time):5.1f}s "
              f"-> difficulty {float(new_diff):.4f} ({direction}, "
              f"adjustment {float(-adjustment):+.4f})")

    print("\nObservation:")
    print("- blocks slower than 60s  -> difficulty rises  (harder PoW pulls block time down)")
    print("- blocks faster than 60s  -> difficulty falls  (easier PoW lets block time rise)")
    print("- result: block time is steered back toward the 60s target")
    print("- a long block drought would also trigger difficulty.py's emergency drop logic")


if __name__ == "__main__":
    main()
