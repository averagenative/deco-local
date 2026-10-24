"""The desktop app's themes: the same five palettes as the web UI (four dark, one light),
applied as an application-wide GTK stylesheet."""

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gtk  # noqa: E402

# Same tokens as web/index.html: background, raised surface, borders, text, muted text,
# accent (and its translucent form), text on the accent, warning, and error.
PALETTES = {
    "Terminal": dict(dark=True, bg="#080c10", panel="#0e151b", border="rgba(255,255,255,0.09)", text="#c8d6e0",
                     strong="#eef5fa", muted="#7d909e", accent="#00d1ff", accent_dim="rgba(0,209,255,0.14)",
                     on_accent="#031018", title="#00ff41", warn="#ffb020", bad="#ff5a6a", input="rgba(255,255,255,0.05)"),
    "Midnight": dict(dark=True, bg="#1a1b26", panel="#20222f", border="rgba(169,177,214,0.15)", text="#c0caf5",
                     strong="#e6e9ff", muted="#8a93bd", accent="#7aa2f7", accent_dim="rgba(122,162,247,0.16)",
                     on_accent="#11131c", title="#bb9af7", warn="#e0af68", bad="#f7768e", input="rgba(255,255,255,0.04)"),
    "Amber CRT": dict(dark=True, bg="#0d0a05", panel="#17120a", border="rgba(255,176,0,0.15)", text="#f2d9a6",
                      strong="#fff1d0", muted="#ad9161", accent="#ffb000", accent_dim="rgba(255,176,0,0.14)",
                      on_accent="#1a1100", title="#ffb000", warn="#ff8a3d", bad="#ff5c4d", input="rgba(255,176,0,0.05)"),
    "Dracula": dict(dark=True, bg="#191622", panel="#221e2e", border="rgba(255,255,255,0.1)", text="#e2dcef",
                    strong="#f8f8f2", muted="#9d93b8", accent="#ff79c6", accent_dim="rgba(255,121,198,0.15)",
                    on_accent="#1b0f17", title="#bd93f9", warn="#f1fa8c", bad="#ff5555", input="rgba(255,255,255,0.04)"),
    "Daylight": dict(dark=False, bg="#f3f6f9", panel="#ffffff", border="#d6dee5", text="#1d2a35",
                     strong="#0b141b", muted="#5b6c79", accent="#0076a8", accent_dim="rgba(0,118,168,0.12)",
                     on_accent="#ffffff", title="#0a7d33", warn="#9a6200", bad="#c62536", input="#ffffff"),
}
THEMES = tuple(PALETTES)
DEFAULT = "Terminal"
# Settings saved by 1.0 to 1.2 named the two GTK variants.
LEGACY = {"Dark": "Terminal", "Light": "Daylight"}

CSS = """
window, window.background {{ background-color: {bg}; color: {text}; }}
headerbar {{ background: {panel}; color: {strong}; border-bottom: 1px solid {border}; box-shadow: none; }}
headerbar .title {{ color: {title}; font-weight: bold; }}
.dim-label {{ color: {muted}; opacity: 1; }}
label.title-4 {{ color: {strong}; }}
label.heading {{ color: {muted}; }}
.warning {{ color: {warn}; }}
.error {{ color: {bad}; }}
separator {{ background: {border}; min-width: 1px; min-height: 1px; }}
stacksidebar, stacksidebar list {{ background: {bg}; }}
stacksidebar row {{ color: {text}; border-radius: 8px; margin: 2px 6px; padding: 6px 10px; }}
stacksidebar row:hover {{ background: {accent_dim}; }}
stacksidebar row:selected {{ background: {accent_dim}; color: {strong}; box-shadow: inset 3px 0 {accent}; }}
frame > border {{ border: 1px solid {border}; border-radius: 10px; }}
frame > label {{ color: {strong}; font-weight: bold; }}
columnview, columnview > listview {{ background: {panel}; color: {text}; }}
columnview > header > button {{ background: {panel}; color: {muted}; border-color: {border}; box-shadow: none; }}
columnview > listview > row:hover {{ background: {accent_dim}; }}
columnview > listview > row:selected {{ background: {accent_dim}; color: {strong}; }}
columnview > listview > row > cell {{ border-color: {border}; }}
entry, spinbutton, searchbar entry {{ background: {input}; color: {text}; border: 1px solid {border}; box-shadow: none; }}
entry:focus-within, spinbutton:focus-within {{ border-color: {accent}; outline-color: {accent}; }}
entry image, spinbutton button {{ color: {muted}; }}
button {{ background: {panel}; color: {text}; border: 1px solid {border}; box-shadow: none; }}
button:hover {{ background: {accent_dim}; color: {strong}; }}
button.suggested-action {{ background: {accent}; color: {on_accent}; border-color: {accent}; font-weight: bold; }}
button.suggested-action:hover {{ background: {accent}; color: {on_accent}; }}
button:disabled {{ opacity: 0.5; }}
dropdown > button {{ background: {input}; }}
switch {{ background: {input}; border: 1px solid {border}; }}
switch:checked {{ background: {accent}; border-color: {accent}; }}
switch > slider {{ background: {strong}; }}
switch:checked > slider {{ background: {on_accent}; }}
checkbutton check {{ background: {input}; border: 1px solid {border}; }}
checkbutton check:checked {{ background: {accent}; border-color: {accent}; color: {on_accent}; }}
popover > contents, popover > arrow {{ background: {panel}; color: {text}; border: 1px solid {border}; }}
popover row:hover, popover row:selected {{ background: {accent_dim}; color: {strong}; }}
.app-notification {{ background: {panel}; color: {strong}; border: 1px solid {border}; border-radius: 10px; }}
scrollbar slider {{ background: {muted}; }}
spinner {{ color: {accent}; }}
"""

_provider = None


def apply(name):
    """Apply a theme by name to the whole app; unknown names fall back to the default."""
    global _provider
    name = LEGACY.get(name, name)
    palette = PALETTES.get(name) or PALETTES[DEFAULT]
    Gtk.Settings.get_default().set_property("gtk-application-prefer-dark-theme", palette["dark"])
    css = CSS.format(**palette)
    if _provider is None:
        _provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), _provider,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    if hasattr(_provider, "load_from_string"):
        _provider.load_from_string(css)
    else:
        _provider.load_from_data(css, -1)
    return name if name in PALETTES else DEFAULT
