"""Check round marks and labels for the profile viewer's linear axes."""

import pytest

from ui.profile_ticks import profile_ticks


@pytest.mark.parametrize(
    ("low", "high", "intervals", "expected"),
    [
        (-4.13369, 40.6266, 3, [(0, "0"), (20, "20"), (40, "40")]),
        (-105.296, 114.998, 3, [(-100, "-100"), (0, "0"), (100, "100")]),
        (86, 698, 5, [(200, "200"), (400, "400"), (600, "600")]),
        (
            -0.31,
            0.11,
            5,
            [(-0.3, "-0.3"), (-0.2, "-0.2"), (-0.1, "-0.1"), (0, "0.0"), (0.1, "0.1")],
        ),
        (
            0.01,
            0.05,
            4,
            [
                (0.01, "0.01"),
                (0.02, "0.02"),
                (0.03, "0.03"),
                (0.04, "0.04"),
                (0.05, "0.05"),
            ],
        ),
        (3, 3, 4, []),
    ],
)
def test_profile_ticks(low, high, intervals, expected):
    assert profile_ticks(low, high, intervals) == expected
