"""Legacy survey-parser adapter; distinct from the historical table parser."""

if __package__ and __package__ != "compat":
    from ..terraworkbench_core import survey_text_import as _implementation
else:
    from terraworkbench_core import survey_text_import as _implementation

globals().update(
    {
        name: value
        for name, value in vars(_implementation).items()
        if not name.startswith("__")
    }
)
