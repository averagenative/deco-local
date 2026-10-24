"""Reusable GTK4 widgets: a sortable column-view table over plain python row dicts."""

from gi.repository import GObject, Gio, Gtk, Pango


class FormDialog(Gtk.Window):
    """A small modal form: labeled entries + Cancel/Save.

    fields: list of (key, label, default) or (key, label, default, extra), where extra is
    True for a masked secret entry or a list of choices for a drop-down. on_submit(values:
    dict) is called with the values when Save is pressed; the dialog closes automatically.
    """

    def __init__(self, parent, title, fields, on_submit, submit_label="Save", note=None):
        super().__init__(title=title, transient_for=parent, modal=True)
        self.set_default_size(360, -1)
        self._on_submit = on_submit
        self._entries = {}

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(16)
        box.set_margin_end(16)

        if note:
            hint = Gtk.Label(label=note, xalign=0, wrap=True, max_width_chars=48)
            hint.add_css_class("dim-label")
            box.append(hint)

        grid = Gtk.Grid(row_spacing=8, column_spacing=10)
        for i, (key, label, default, *extra) in enumerate(fields):
            lbl = Gtk.Label(label=label, xalign=0)
            kind = extra[0] if extra else None
            if isinstance(kind, (list, tuple)):
                entry = Gtk.DropDown.new_from_strings(list(kind))
                entry.set_hexpand(True)
                if default in kind:
                    entry.set_selected(list(kind).index(default))
                entry._choices = list(kind)
            else:
                entry = Gtk.PasswordEntry(hexpand=True, show_peek_icon=True) if kind is True else Gtk.Entry(hexpand=True)
                entry.connect("activate", self._submit)
                if default is not None:
                    entry.set_text(str(default))
            grid.attach(lbl, 0, i, 1, 1)
            grid.attach(entry, 1, i, 1, 1)
            self._entries[key] = entry
        box.append(grid)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8,
                          halign=Gtk.Align.END)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda _b: self.close())
        save = Gtk.Button(label=submit_label)
        save.add_css_class("suggested-action")
        save.connect("clicked", self._submit)
        buttons.append(cancel)
        buttons.append(save)
        box.append(buttons)

        self.set_child(box)

    def _submit(self, _btn):
        values = {k: (e._choices[e.get_selected()] if isinstance(e, Gtk.DropDown) else e.get_text().strip())
                  for k, e in self._entries.items()}
        self.close()
        self._on_submit(values)


class Row(GObject.Object):
    """A GObject wrapper carrying an arbitrary python payload for list models."""

    __gtype_name__ = "DecoRow"

    def __init__(self, data):
        super().__init__()
        self.data = data


class Table:
    """A Gtk.ColumnView backed by a Gio.ListStore of Row objects.

    columns: list of (title, getter, sortable) or (title, getter, sortable, sort_key), where
    getter(data) -> str is what the cell shows and sort_key(data), when given, is what the
    column sorts by (for example a number behind "1.8 MB/s"). set_filter() hides rows.
    widths maps a column title to a fixed width in pixels; the other columns share the rest.
    """

    def __init__(self, columns, on_activate=None, widths=None):
        self._columns = columns
        self.store = Gio.ListStore(item_type=Row)

        self.view = Gtk.ColumnView(hexpand=True, vexpand=True)
        self.view.set_show_row_separators(True)
        self.view.set_show_column_separators(True)

        self._filter_fn = None
        self._filter = Gtk.CustomFilter.new(lambda item, *_: self._filter_fn is None or bool(self._filter_fn(item.data)))
        filter_model = Gtk.FilterListModel(model=self.store, filter=self._filter)
        sort_model = Gtk.SortListModel(model=filter_model, sorter=self.view.get_sorter())
        self.selection = Gtk.SingleSelection(model=sort_model)
        self.view.set_model(self.selection)

        self._by_title = {}
        for title, getter, sortable, *key in columns:
            col = self._make_column(title, getter, sortable, key[0] if key else None)
            self._by_title[title] = col
            if widths and title in widths:
                col.set_fixed_width(widths[title])
                col.set_expand(False)
            self.view.append_column(col)

        if on_activate is not None:
            self.view.connect("activate", lambda _v, pos: on_activate(self.selected()))

        self.scroller = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        self.scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.scroller.set_child(self.view)

    def _make_column(self, title, getter, sortable, sort_key=None):
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._on_setup)
        factory.connect("bind", self._on_bind, getter)
        col = Gtk.ColumnViewColumn(title=title, factory=factory)
        col.set_resizable(True)
        col.set_expand(True)
        if sortable:
            col.set_sorter(Gtk.CustomSorter.new(self._compare_factory(sort_key or getter)))
        return col

    @staticmethod
    def _on_setup(_factory, item):
        # Ellipsize so columns can shrink to fit the window; the tooltip shows the full text.
        label = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END, width_chars=4)
        label.set_margin_start(6)
        label.set_margin_end(6)
        item.set_child(label)

    @staticmethod
    def _on_bind(_factory, item, getter):
        row = item.get_item()
        text = str(getter(row.data))
        label = item.get_child()
        label.set_text(text)
        label.set_tooltip_text(text if len(text) > 12 else None)

    @staticmethod
    def _compare_factory(getter):
        def compare(a, b, _user_data=None):
            va, vb = getter(a.data), getter(b.data)
            # numeric-aware where possible, else string
            try:
                fa, fb = float(va), float(vb)
                return (fa > fb) - (fa < fb)
            except (TypeError, ValueError):
                sa, sb = str(va).lower(), str(vb).lower()
                return (sa > sb) - (sa < sb)

        return compare

    def set_filter(self, fn):
        """Show only rows where fn(data) is true; None shows every row."""
        self._filter_fn = fn
        self._filter.changed(Gtk.FilterChange.DIFFERENT)

    def sort_by(self, title, descending=False):
        self.view.sort_by_column(self._by_title[title],
                                 Gtk.SortType.DESCENDING if descending else Gtk.SortType.ASCENDING)

    def visible_count(self):
        return self.selection.get_n_items()

    def set_rows(self, items):
        """Replace all rows with `items` (list of payloads)."""
        self.store.remove_all()
        for it in items:
            self.store.append(Row(it))

    def selected(self):
        """The payload of the selected row, or None."""
        item = self.selection.get_selected_item()
        return item.data if item is not None else None


def min_to_hhmm(m):
    n = int(m or 0)
    return f"{n // 60 % 24:02d}:{n % 60:02d}"


def hhmm_to_min(text):
    h, _, m = text.strip().partition(":")
    hours, minutes = int(h), int(m or 0)
    if not (0 <= hours < 24 and 0 <= minutes < 60):
        raise ValueError(f"{text!r} is not a time (HH:MM)")
    return hours * 60 + minutes


def kv_grid(pairs):
    """A two-column grid of dim keys and selectable values."""
    grid = Gtk.Grid(row_spacing=4, column_spacing=14)
    for i, (key, value) in enumerate(pairs):
        k = Gtk.Label(label=key, xalign=0)
        k.add_css_class("dim-label")
        v = Gtk.Label(label="-" if value in (None, "") else str(value), xalign=0, selectable=True, wrap=True)
        grid.attach(k, 0, i, 1, 1)
        grid.attach(v, 1, i, 1, 1)
    return grid


def group_frame(title, desc=None):
    """A titled frame with a vertical box inside; returns (frame, box)."""
    frame = Gtk.Frame(label=title)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    for side in ("top", "bottom", "start", "end"):
        getattr(box, f"set_margin_{side}")(10)
    if desc:
        d = Gtk.Label(label=desc, xalign=0, wrap=True, max_width_chars=34, width_chars=34)
        d.add_css_class("dim-label")
        box.append(d)
    frame.set_child(box)
    return frame, box


class SettingsGroup:
    """One Deco setting as a titled group of controls with a Save button.

    fields: list of (path, kind, label); kind is "toggle", "time" (minutes after midnight,
    shown as HH:MM), or "mbps" (stored as Kbps, 1 Mbps = 1024). A dotted path such as
    "setting.time" edits one field of a nested object. on_save(changes) receives only the
    changed fields; call set_value() with the new value afterwards.
    """

    def __init__(self, title, desc, fields, on_save, validate=None):
        self.frame, box = group_frame(title, desc)
        self._fields = fields
        self._on_save = on_save
        self._validate = validate
        self._controls = {}
        self._value = None
        for path, kind, label in fields:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            row.append(Gtk.Label(label=label, xalign=0, hexpand=True))
            if kind == "toggle":
                ctl = Gtk.Switch(valign=Gtk.Align.CENTER)
            elif kind == "time":
                ctl = Gtk.Entry(width_chars=6, max_width_chars=6, placeholder_text="HH:MM")
            else:
                ctl = Gtk.SpinButton.new_with_range(0, 10000, 1)
            row.append(ctl)
            box.append(row)
            self._controls[path] = (kind, ctl)
        self._error = Gtk.Label(xalign=0, wrap=True)
        self._error.add_css_class("error")
        self._error.set_visible(False)
        box.append(self._error)
        self._save = Gtk.Button(label="Save", halign=Gtk.Align.END)
        self._save.add_css_class("suggested-action")
        self._save.connect("clicked", self._clicked)
        box.append(self._save)
        self.frame.set_sensitive(False)

    @staticmethod
    def _get(obj, path):
        for k in path.split("."):
            obj = obj.get(k) if isinstance(obj, dict) else None
        return obj

    def set_value(self, value):
        """Show `value` (the setting as the Deco returns it), or an error dict."""
        self._value = value if isinstance(value, dict) else None
        failed = not self._value or "_error" in self._value
        self._error.set_visible(failed and bool(value))
        if failed:
            self._error.set_text((value or {}).get("_error", "") if isinstance(value, dict) else "")
            self.frame.set_sensitive(bool(value))
            self._save.set_sensitive(False)
            return
        for path, (kind, ctl) in self._controls.items():
            v = self._get(self._value, path)
            if kind == "toggle":
                ctl.set_active(bool(v))
            elif kind == "time":
                ctl.set_text(min_to_hhmm(v))
            else:
                ctl.set_value(round((int(v or 0)) / 1024))
        self._save.set_sensitive(True)
        self.frame.set_sensitive(True)

    def _clicked(self, _btn):
        changes = {}
        try:
            for path, (kind, ctl) in self._controls.items():
                old = self._get(self._value, path)
                if kind == "toggle":
                    new, same = ctl.get_active(), bool(old) == ctl.get_active()
                elif kind == "time":
                    new = hhmm_to_min(ctl.get_text())
                    same = int(old or 0) == new
                else:
                    new = int(ctl.get_value()) * 1024
                    same = round(int(old or 0) / 1024) * 1024 == new
                if same:
                    continue
                top, _, sub = path.partition(".")
                if sub:
                    changes.setdefault(top, dict(self._value.get(top) or {}))[sub] = new
                else:
                    changes[top] = new
        except ValueError as e:
            self._show_error(str(e))
            return
        if not changes:
            return
        problem = self._validate({**self._value, **changes}) if self._validate else None
        if problem:
            self._show_error(problem)
            return
        self._error.set_visible(False)
        self._on_save(changes)

    def _show_error(self, text):
        self._error.set_text(text)
        self._error.set_visible(True)
