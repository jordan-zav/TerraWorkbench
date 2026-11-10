"""Compatibility import for the shared scientific core; no numerical logic."""

if __package__ and __package__ != "compat":
    from ..terraworkbench_core import preprocessing as _implementation
else:
    from terraworkbench_core import preprocessing as _implementation

globals().update(
    {
        name: value
        for name, value in vars(_implementation).items()
        if not name.startswith("__")
    }
)
