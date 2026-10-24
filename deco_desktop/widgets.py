"""Reusable GTK4 widgets: a sortable column-view table over plain python row dicts."""

from gi.repository import GObject, Gio, Gtk


class FormDialog(Gtk.Window):
    """A small modal form: labeled entries + Cancel/Save.

    fields: list of (key, label, default) or (key, label, default, secret); secret
    entries mask their text. on_submit(values: dict) is called with the entry values
    when Save is pressed; the dialog closes automatically.
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
        for i, (key, label, default, *secret) in enumerate(fields):
            lbl = Gtk.Label(label=label, xalign=0)
            entry = Gtk.PasswordEntry(hexpand=True, show_peek_icon=True) if any(secret) else Gtk.Entry(hexpand=True)
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
        values = {k: e.get_text().strip() for k, e in self._entries.items()}
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

    columns: list of (title, getter, sortable) where getter(data) -> str.
    """

    def __init__(self, columns, on_activate=None):
        self._columns = columns
        self.store = Gio.ListStore(item_type=Row)

        self.view = Gtk.ColumnView(hexpand=True, vexpand=True)
        self.view.set_show_row_separators(True)
        self.view.set_show_column_separators(True)

        sort_model = Gtk.SortListModel(model=self.store, sorter=self.view.get_sorter())
        self.selection = Gtk.SingleSelection(model=sort_model)
        self.view.set_model(self.selection)

        for title, getter, sortable in columns:
            self.view.append_column(self._make_column(title, getter, sortable))

        if on_activate is not None:
            self.view.connect("activate", lambda _v, pos: on_activate(self.selected()))

        self.scroller = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        self.scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.scroller.set_child(self.view)

    def _make_column(self, title, getter, sortable):
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._on_setup)
        factory.connect("bind", self._on_bind, getter)
        col = Gtk.ColumnViewColumn(title=title, factory=factory)
        col.set_resizable(True)
        col.set_expand(True)
        if sortable:
            col.set_sorter(Gtk.CustomSorter.new(self._compare_factory(getter)))
        return col

    @staticmethod
    def _on_setup(_factory, item):
        label = Gtk.Label(xalign=0)
        label.set_margin_start(6)
        label.set_margin_end(6)
        item.set_child(label)

    @staticmethod
    def _on_bind(_factory, item, getter):
        row = item.get_item()
        item.get_child().set_text(str(getter(row.data)))

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

    def set_rows(self, items):
        """Replace all rows with `items` (list of payloads)."""
        self.store.remove_all()
        for it in items:
            self.store.append(Row(it))

    def selected(self):
        """The payload of the selected row, or None."""
        item = self.selection.get_selected_item()
        return item.data if item is not None else None
