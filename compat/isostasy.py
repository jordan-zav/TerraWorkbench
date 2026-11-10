"""Compatibility import for the shared scientific core; no numerical logic."""
if __package__ and __package__ != "compat":
    from ..terraworkbench_core import isostasy as _implementation
else:
    from terraworkbench_core import isostasy as _implementation

# Preserve legacy public and private imports used by the plugin and recipes.
globals().update({name: value for name, value in vars(_implementation).items()
                  if not name.startswith("__")})
