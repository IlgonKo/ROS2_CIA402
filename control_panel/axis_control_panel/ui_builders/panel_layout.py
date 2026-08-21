"""Top-level panel layout builder."""

from tkinter import ttk


class PanelLayoutMixin:
    def _build_panel_layout(self):
        style = ttk.Style(self.root)
        style.configure("Connected.TButton", foreground="green", background="#2e7d32")
        style.map(
            "Connected.TButton",
            foreground=[
                ("active", "green"),
                ("pressed", "green"),
                ("disabled", "green"),
            ],
            background=[
                ("active", "#43a047"),
                ("pressed", "#1b5e20"),
                ("disabled", "#2e7d32"),
            ],
        )

        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 10))
        ttk.Label(
            header,
            text="Axis Control Panel",
            font=("TkDefaultFont", 12, "bold"),
        ).pack(side="left")
        ttk.Button(
            header,
            textvariable=self.command_authority_button_var,
            command=self.toggle_command_authority,
        ).pack(side="left", padx=(14, 4))
        ttk.Button(
            header,
            text="Bus Reconnect",
            command=self.bus_reconnect,
        ).pack(side="left", padx=(8, 4))
        ttk.Button(
            header,
            text="Server Reset",
            command=self.server_reset,
        ).pack(side="left", padx=4)
        ttk.Button(
            header,
            text="Server Restart",
            command=self.server_restart,
        ).pack(side="left", padx=4)
        ttk.Label(header, textvariable=self.command_authority_var).pack(
            side="left",
            padx=4,
        )
        ttk.Label(header, text="Host").pack(side="left", padx=(14, 4))
        ttk.Entry(
            header,
            textvariable=self.server_host_var,
            width=18,
        ).pack(side="left")
        ttk.Label(header, text="Port").pack(side="left", padx=(8, 4))
        ttk.Entry(
            header,
            textvariable=self.server_port_var,
            justify="right",
            width=7,
        ).pack(side="left")
        self.connection_button = ttk.Button(
            header,
            textvariable=self.connection_button_var,
            command=self.toggle_server_connection,
        )
        self.connection_button.pack(side="left", padx=(6, 4))
        ttk.Label(header, textvariable=self.connection_var).pack(side="right")
        ttk.Label(header, textvariable=self.scale_var).pack(side="right", padx=12)

        self.axis_selector_notebook = ttk.Notebook(outer)
        self.axis_selector_notebook.pack(fill="x", pady=(0, 10))
        for axis_name in self.axis_names:
            axis_tab = ttk.Frame(self.axis_selector_notebook)
            self.axis_selector_notebook.add(axis_tab, text=axis_name)
        multi_tab = ttk.Frame(self.axis_selector_notebook)
        self.axis_selector_notebook.add(multi_tab, text="Multi Axis")
        self.axis_selector_notebook.bind(
            "<<NotebookTabChanged>>",
            self.on_axis_selector_changed,
        )

        self.single_axis_area = ttk.Frame(outer)
        self.single_axis_area.pack(fill="both", expand=True)
        self.multi_axis_area = ttk.Frame(outer)
