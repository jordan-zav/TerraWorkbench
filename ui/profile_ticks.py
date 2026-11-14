"""Readable tick positions and labels for linear profile axes."""

from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
import math


def profile_ticks(low, high, intervals):
    """Return in-range ticks at multiples of a 1, 2 or 5 power-of-ten step."""
    if not (math.isfinite(low) and math.isfinite(high) and low < high):
        return []
    lower, upper = Decimal(str(low)), Decimal(str(high))
    ideal = (upper - lower) / intervals
    scale = Decimal(1).scaleb(ideal.adjusted())
    step = next(
        scale * multiple for multiple in (1, 2, 5, 10) if scale * multiple >= ideal
    )
    first = int((lower / step).to_integral_value(rounding=ROUND_CEILING))
    last = int((upper / step).to_integral_value(rounding=ROUND_FLOOR))
    decimals = max(0, -step.adjusted())
    use_exponent = decimals > 6 or max(abs(lower), abs(upper)) >= 10**9
    ticks = []
    for index in range(first, last + 1):
        value = index * step
        label = (
            format(value.normalize(), "g")
            if use_exponent
            else format(value, f".{decimals}f")
        )
        ticks.append((float(value), label))
    return ticks
