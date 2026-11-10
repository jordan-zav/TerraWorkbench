"""Compatibility import for the standalone scientific inversion engine."""

if __package__ and __package__ != "compat":
    from ..terraworkbench_core import inversion as _implementation
else:
    from terraworkbench_core import inversion as _implementation

globals().update({name: value for name, value in vars(_implementation).items()
                  if not name.startswith("__")})
