"""Compatibility import for the shared scientific core; no storage logic."""

if __package__ and __package__ != "compat":
    from ..terraworkbench_core import survey_store as _implementation
else:
    from terraworkbench_core import survey_store as _implementation

globals().update(
    {
        name: value
        for name, value in vars(_implementation).items()
        if not name.startswith("__")
    }
)
