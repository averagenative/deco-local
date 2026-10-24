"""Feature screens for the Deco desktop app."""

from gi.repository import Gtk


class Screen(Gtk.Box):
    """Base screen: a top toolbar (title, spinner, actions) over a content area."""

    def __init__(self, window, title):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.window = window
        self.set_margin_top(10)
        self.set_margin_bottom(10)
        self.set_margin_start(10)
        self.set_margin_end(10)
        self.set_spacing(8)

        self.toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        heading = Gtk.Label(label=title, xalign=0)
        heading.add_css_class("title-4")
        heading.set_hexpand(True)
        self.toolbar.append(heading)

        self._spinner = Gtk.Spinner()
        self.toolbar.append(self._spinner)

        self._refresh_btn = Gtk.Button(label="Refresh")
        self._refresh_btn.connect("clicked", lambda _b: self.refresh())
        self.toolbar.append(self._refresh_btn)

        self.append(self.toolbar)

    # ---- helpers for subclasses ----
    def add_action(self, label, handler):
        btn = Gtk.Button(label=label)
        btn.connect("clicked", lambda _b: handler())
        self.toolbar.append(btn)
        return btn

    def set_busy(self, busy):
        self._refresh_btn.set_sensitive(not busy)
        if busy:
            self._spinner.start()
        else:
            self._spinner.stop()

    def run_call(self, fn, on_success, label=None):
        """Submit a backend call with busy state + error handling wired up."""
        if not self.window.connected:
            self.window.toast("Not connected.")
            return
        self.set_busy(True)

        def success(result):
            self.set_busy(False)
            on_success(result)
            return False

        def error(exc):
            self.set_busy(False)
            self.window.toast(f"Error: {exc}", timeout=6)
            return False

        self.window.submit(fn, on_success=success, on_error=error, label=label)

    def confirm(self, message, on_yes, destructive_label="Delete"):
        """Show a modal confirm dialog; call on_yes() if the user confirms."""
        dlg = Gtk.AlertDialog()
        dlg.set_message(message)
        dlg.set_buttons(["Cancel", destructive_label])
        dlg.set_default_button(0)
        dlg.set_cancel_button(0)

        def done(d, res):
            try:
                if d.choose_finish(res) == 1:
                    on_yes()
            except Exception:
                pass

        dlg.choose(self.window, None, done)

    # ---- overridable ----
    def refresh(self):
        raise NotImplementedError

    def on_disconnected(self):
        pass
