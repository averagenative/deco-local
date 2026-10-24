"""deco_desktop — native GTK4 desktop client for the strictly-local Deco backend.

Thin UI over the proven `deco_api.DecoLocal` API. All device I/O runs on a single
serialized worker thread (see `backend.py`); the GTK UI thread only ever touches
results marshaled back via `GLib.idle_add`.
"""

import gi

gi.require_version("Gtk", "4.0")

__all__ = ["main", "__version__"]
__version__ = "1.2.0"


def main(argv=None):
    from .app import main as _main
    return _main(argv)
