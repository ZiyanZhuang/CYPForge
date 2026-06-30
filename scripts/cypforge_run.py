"""Thin shim; prefer the installed `cypforge` console script.

This file exists only so that legacy invocations of
``python scripts/cypforge_run.py ...`` continue to work after the CLI was
moved into the ``cypforge_core.cli`` package. New work should use
``cypforge ...`` (after ``pip install -e .``) or ``python -m cypforge_core.cli``.

For backward compatibility this module re-binds every attribute of
``cypforge_core.cli`` (including underscore-prefixed helpers such as
``_build_parser``) onto this module's namespace, so callers that load this
file via ``importlib.util.spec_from_file_location`` continue to see the
historic public + private surface.
"""
import sys
import warnings
from pathlib import Path

warnings.warn(
    "scripts/cypforge_run.py is a thin shim; prefer 'cypforge' after `pip install -e .`",
    DeprecationWarning,
    stacklevel=2,
)

# Legacy bootstrap: when invoked as `python scripts/cypforge_run.py ...` from a
# source checkout that hasn't been `pip install`ed, src/ is not on sys.path.
# Add it so `import cypforge_core` resolves. After `pip install -e .` the import
# would succeed anyway and this prepend is a no-op (already on path).
_SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if _SRC_DIR.is_dir() and str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from cypforge_core import cli as _cli_module

# Re-bind every non-dunder attribute (functions, classes, module-level constants)
# so legacy spec_from_file_location loaders see _build_parser, cmd_init, etc.
for _name in dir(_cli_module):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_cli_module, _name)
del _name

main = _cli_module.main

if __name__ == "__main__":
    raise SystemExit(main())
