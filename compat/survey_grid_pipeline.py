"""Compatibility import for the shared scientific core; no processing logic."""

if __package__ and __package__ != "compat":
    from ..terraworkbench_core import survey_grid_pipeline as _implementation
else:
    from terraworkbench_core import survey_grid_pipeline as _implementation

globals().update(
    {
        name: value
        for name, value in vars(_implementation).items()
        if not name.startswith("__")
    }
)
