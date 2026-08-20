import re
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

if __package__ in {None, ""}:
    project_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(project_root))

from control_panel.io_control_panel.client import MotionServerClient
from control_panel.io_control_panel.config import read_runtime_config


GUI_PERIOD_MS = 500
AP_TYPE_LENGTHS = {
    "int8": "1",
    "uint8": "1",
    "uint16": "2",
    "int16": "2",
    "int32": "4",
    "uint32": "4",
    "float32": "4",
}


class IOControlPanel:
    def __init__(self, root, client):
        self.root = root
        self.client = client
        self.status = None
        self.device_var = tk.StringVar()
        self.slot_var = tk.StringVar()
        self.channel_var = tk.StringVar(value="0")
        self.output_value_var = tk.BooleanVar(value=False)
        self.param_index_var = tk.StringVar(value="0x1000")
        self.param_subindex_var = tk.StringVar(value="0x00")
        self.param_type_var = tk.StringVar(value="uint32")
        self.param_length_var = tk.StringVar(value="12")
        self.param_value_var = tk.StringVar(value="0")
        self.param_result_var = tk.StringVar(value="")
        self.ec_catalog_var = tk.StringVar(value="")
        self.ec_catalog_items = {}
        self.ap_module_var = tk.StringVar(value="1")
        self.ap_parameter_id_var = tk.StringVar(value="791")
        self.ap_instance_var = tk.StringVar(value="0")
        self.ap_length_var = tk.StringVar(value="12")
        self.ap_type_var = tk.StringVar(value="char")
        self.ap_value_var = tk.StringVar(value="0")
        self.ap_result_var = tk.StringVar(value="")
        self.iol_module_var = tk.StringVar(value="4")
        self.iol_port_var = tk.StringVar(value="0")
        self.iol_index_var = tk.StringVar(value="0x0010")
        self.iol_subindex_var = tk.StringVar(value="0x00")
        self.iol_length_var = tk.StringVar(value="4")
        self.iol_type_var = tk.StringVar(value="uint32")
        self.iol_value_var = tk.StringVar(value="0")
        self.iol_result_var = tk.StringVar(value="")
        self.iol_catalog_var = tk.StringVar(value="")
        self.iol_catalog_items = {}
        self.raw_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Disconnected")
        self.command_authority_var = tk.StringVar(value="Authority: unknown")
        self.command_authority_button_var = tk.StringVar(value="Request Authority")
        self.connected = False

        self.root.title("IO Control Panel")
        self.root.geometry("1120x760")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.build_ui()
        self.client.start()
        self.update_gui()

    def build_ui(self):
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill="x")

        ttk.Button(top, text="Refresh", command=self.refresh).pack(side="left")
        ttk.Button(
            top,
            textvariable=self.command_authority_button_var,
            command=self.toggle_command_authority,
        ).pack(side="left", padx=(8, 0))
        ttk.Checkbutton(
            top,
            text="Raw Image",
            variable=self.raw_var,
            command=self.refresh,
        ).pack(side="left", padx=(8, 0))
        ttk.Label(top, textvariable=self.command_authority_var).pack(
            side="left",
            padx=(12, 0),
        )
        ttk.Label(top, textvariable=self.status_var).pack(side="left", padx=(12, 0))

        ttk.Label(top, text=f"{self.client.host}:{self.client.port}").pack(
            side="right"
        )

        command = ttk.LabelFrame(self.root, text="Digital Output", padding=8)
        command.pack(fill="x", padx=8, pady=(0, 8))

        ttk.Label(command, text="I/O").grid(row=0, column=0, sticky="w")
        self.device_combo = ttk.Combobox(
            command,
            textvariable=self.device_var,
            width=12,
            state="readonly",
        )
        self.device_combo.grid(row=0, column=1, padx=4)

        ttk.Label(command, text="Module").grid(row=0, column=2, sticky="w")
        self.slot_combo = ttk.Combobox(
            command,
            textvariable=self.slot_var,
            width=8,
            state="readonly",
        )
        self.slot_combo.grid(row=0, column=3, padx=4)

        ttk.Label(command, text="Channel").grid(row=0, column=4, sticky="w")
        ttk.Entry(command, textvariable=self.channel_var, width=8).grid(
            row=0,
            column=5,
            padx=4,
        )

        ttk.Checkbutton(
            command,
            text="ON",
            variable=self.output_value_var,
        ).grid(row=0, column=6, padx=8)
        ttk.Button(
            command,
            text="Apply",
            command=self.apply_digital_output,
        ).grid(row=0, column=7)

        parameter_tabs = ttk.Notebook(self.root)
        parameter_tabs.pack(fill="x", padx=8, pady=(0, 8))

        parameter = ttk.Frame(parameter_tabs, padding=8)
        parameter_tabs.add(parameter, text="EC Parameter")

        ttk.Label(parameter, text="Catalog").grid(row=0, column=0, sticky="w")
        self.ec_catalog_combo = ttk.Combobox(
            parameter,
            textvariable=self.ec_catalog_var,
            width=36,
            state="readonly",
        )
        self.ec_catalog_combo.grid(row=0, column=1, columnspan=4, sticky="ew", padx=4)
        self.ec_catalog_combo.bind("<<ComboboxSelected>>", self.on_ec_catalog_selected)
        ttk.Button(
            parameter,
            text="Load Catalog",
            command=self.load_ec_catalog,
        ).grid(row=0, column=8, padx=(8, 0))

        self.ec_catalog_detail_text = self.add_detail_text(
            parameter,
            row=1,
            columnspan=12,
        )

        ttk.Label(parameter, text="I/O").grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.param_device_combo = ttk.Combobox(
            parameter,
            textvariable=self.device_var,
            width=12,
            state="readonly",
        )
        self.param_device_combo.grid(row=2, column=1, padx=4, pady=(6, 0))

        ttk.Label(parameter, text="Index").grid(row=2, column=2, sticky="w", pady=(6, 0))
        ttk.Entry(parameter, textvariable=self.param_index_var, width=10).grid(
            row=2,
            column=3,
            padx=4,
            pady=(6, 0),
        )

        ttk.Label(parameter, text="Sub").grid(row=2, column=4, sticky="w", pady=(6, 0))
        ttk.Entry(parameter, textvariable=self.param_subindex_var, width=8).grid(
            row=2,
            column=5,
            padx=4,
            pady=(6, 0),
        )

        ttk.Label(parameter, text="Type").grid(row=2, column=6, sticky="w", pady=(6, 0))
        ttk.Combobox(
            parameter,
            textvariable=self.param_type_var,
            values=(
                "uint8",
                "int8",
                "uint16",
                "int16",
                "int32",
                "uint32",
                "float32",
                "char",
                "string",
            ),
            width=9,
            state="readonly",
        ).grid(row=2, column=7, padx=4, pady=(6, 0))

        ttk.Label(parameter, text="Length").grid(row=2, column=8, sticky="w", pady=(6, 0))
        ttk.Entry(parameter, textvariable=self.param_length_var, width=8).grid(
            row=2,
            column=9,
            padx=4,
            pady=(6, 0),
        )

        ttk.Label(parameter, text="Value").grid(row=2, column=10, sticky="w", pady=(6, 0))
        ttk.Entry(parameter, textvariable=self.param_value_var, width=12).grid(
            row=2,
            column=11,
            padx=4,
            pady=(6, 0),
        )

        ttk.Button(parameter, text="Read", command=self.read_parameter).grid(
            row=2,
            column=12,
            padx=(8, 0),
            pady=(6, 0),
        )
        ttk.Button(parameter, text="Write", command=self.write_parameter).grid(
            row=2,
            column=13,
            padx=4,
            pady=(6, 0),
        )
        ttk.Entry(
            parameter,
            textvariable=self.param_result_var,
            state="readonly",
        ).grid(
            row=3,
            column=0,
            columnspan=14,
            sticky="ew",
            pady=(6, 0),
        )
        parameter.columnconfigure(13, weight=1)

        ap_parameter = ttk.Frame(parameter_tabs, padding=8)
        parameter_tabs.add(ap_parameter, text="AP Parameter")

        ttk.Label(ap_parameter, text="I/O").grid(row=0, column=0, sticky="w")
        self.ap_device_combo = ttk.Combobox(
            ap_parameter,
            textvariable=self.device_var,
            width=12,
            state="readonly",
        )
        self.ap_device_combo.grid(row=0, column=1, padx=4)

        ttk.Label(ap_parameter, text="Module").grid(row=0, column=2, sticky="w")
        ttk.Entry(ap_parameter, textvariable=self.ap_module_var, width=8).grid(
            row=0,
            column=3,
            padx=4,
        )

        ttk.Label(ap_parameter, text="Parameter ID").grid(row=0, column=4, sticky="w")
        ttk.Entry(ap_parameter, textvariable=self.ap_parameter_id_var, width=14).grid(
            row=0,
            column=5,
            padx=4,
        )

        ttk.Label(ap_parameter, text="Instance").grid(row=0, column=6, sticky="w")
        ttk.Entry(ap_parameter, textvariable=self.ap_instance_var, width=8).grid(
            row=0,
            column=7,
            padx=4,
        )

        ttk.Label(ap_parameter, text="Length").grid(row=0, column=8, sticky="w")
        ttk.Entry(ap_parameter, textvariable=self.ap_length_var, width=8).grid(
            row=0,
            column=9,
            padx=4,
        )

        ttk.Label(ap_parameter, text="Type").grid(row=1, column=0, sticky="w")
        self.ap_type_combo = ttk.Combobox(
            ap_parameter,
            textvariable=self.ap_type_var,
            values=(
                "bytes",
                "char",
                "uint8",
                "int8",
                "uint16",
                "int32",
                "uint32",
                "float32",
            ),
            width=9,
            state="readonly",
        )
        self.ap_type_combo.grid(row=1, column=1, padx=4, pady=(6, 0))
        self.ap_type_combo.bind("<<ComboboxSelected>>", self.on_ap_type_changed)

        ttk.Label(ap_parameter, text="Value").grid(row=1, column=2, sticky="w", pady=(6, 0))
        ttk.Entry(ap_parameter, textvariable=self.ap_value_var, width=18).grid(
            row=1,
            column=3,
            columnspan=2,
            sticky="w",
            padx=4,
            pady=(6, 0),
        )

        ttk.Button(ap_parameter, text="Read", command=self.read_ap_parameter).grid(
            row=1,
            column=5,
            padx=(8, 0),
            pady=(6, 0),
        )
        ttk.Button(ap_parameter, text="Write", command=self.write_ap_parameter).grid(
            row=1,
            column=6,
            padx=4,
            pady=(6, 0),
        )
        ttk.Entry(
            ap_parameter,
            textvariable=self.ap_result_var,
            state="readonly",
        ).grid(
            row=2,
            column=0,
            columnspan=10,
            sticky="ew",
            pady=(6, 0),
        )
        ap_parameter.columnconfigure(9, weight=1)

        iol_parameter = ttk.Frame(parameter_tabs, padding=8)
        parameter_tabs.add(iol_parameter, text="IOL Parameter")

        ttk.Label(iol_parameter, text="Catalog").grid(row=0, column=0, sticky="w")
        self.iol_catalog_combo = ttk.Combobox(
            iol_parameter,
            textvariable=self.iol_catalog_var,
            width=36,
            state="readonly",
        )
        self.iol_catalog_combo.grid(row=0, column=1, columnspan=4, sticky="ew", padx=4)
        self.iol_catalog_combo.bind("<<ComboboxSelected>>", self.on_iol_catalog_selected)
        ttk.Button(
            iol_parameter,
            text="Load Catalog",
            command=self.load_iol_catalog,
        ).grid(row=0, column=8, padx=(8, 0))

        self.iol_catalog_detail_text = self.add_detail_text(
            iol_parameter,
            row=1,
            columnspan=10,
        )

        ttk.Label(iol_parameter, text="I/O").grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.iol_device_combo = ttk.Combobox(
            iol_parameter,
            textvariable=self.device_var,
            width=12,
            state="readonly",
        )
        self.iol_device_combo.grid(row=2, column=1, padx=4, pady=(6, 0))

        ttk.Label(iol_parameter, text="Module").grid(row=2, column=2, sticky="w", pady=(6, 0))
        ttk.Entry(iol_parameter, textvariable=self.iol_module_var, width=8).grid(
            row=2,
            column=3,
            padx=4,
            pady=(6, 0),
        )

        ttk.Label(iol_parameter, text="Port").grid(row=2, column=4, sticky="w", pady=(6, 0))
        ttk.Entry(iol_parameter, textvariable=self.iol_port_var, width=8).grid(
            row=2,
            column=5,
            padx=4,
            pady=(6, 0),
        )

        ttk.Label(iol_parameter, text="Index").grid(row=2, column=6, sticky="w", pady=(6, 0))
        ttk.Entry(iol_parameter, textvariable=self.iol_index_var, width=10).grid(
            row=2,
            column=7,
            padx=4,
            pady=(6, 0),
        )

        ttk.Label(iol_parameter, text="Sub").grid(row=2, column=8, sticky="w", pady=(6, 0))
        ttk.Entry(iol_parameter, textvariable=self.iol_subindex_var, width=8).grid(
            row=2,
            column=9,
            padx=4,
            pady=(6, 0),
        )

        ttk.Label(iol_parameter, text="Length").grid(row=3, column=0, sticky="w")
        ttk.Entry(iol_parameter, textvariable=self.iol_length_var, width=8).grid(
            row=3,
            column=1,
            padx=4,
            pady=(6, 0),
        )

        ttk.Label(iol_parameter, text="Type").grid(row=3, column=2, sticky="w", pady=(6, 0))
        self.iol_type_combo = ttk.Combobox(
            iol_parameter,
            textvariable=self.iol_type_var,
            values=(
                "bytes",
                "char",
                "uint8",
                "int8",
                "uint16",
                "int16",
                "int32",
                "uint32",
                "float32",
            ),
            width=9,
            state="readonly",
        )
        self.iol_type_combo.grid(row=3, column=3, padx=4, pady=(6, 0))
        self.iol_type_combo.bind("<<ComboboxSelected>>", self.on_iol_type_changed)

        ttk.Label(iol_parameter, text="Value").grid(row=3, column=4, sticky="w", pady=(6, 0))
        ttk.Entry(iol_parameter, textvariable=self.iol_value_var, width=18).grid(
            row=3,
            column=5,
            columnspan=2,
            sticky="w",
            padx=4,
            pady=(6, 0),
        )

        ttk.Button(iol_parameter, text="Read", command=self.read_iol_parameter).grid(
            row=3,
            column=7,
            padx=(8, 0),
            pady=(6, 0),
        )
        ttk.Button(iol_parameter, text="Write", command=self.write_iol_parameter).grid(
            row=3,
            column=8,
            padx=4,
            pady=(6, 0),
        )
        ttk.Entry(
            iol_parameter,
            textvariable=self.iol_result_var,
            state="readonly",
        ).grid(
            row=4,
            column=0,
            columnspan=10,
            sticky="ew",
            pady=(6, 0),
        )
        iol_parameter.columnconfigure(9, weight=1)

        self.tree = ttk.Treeview(
            self.root,
            columns=("value",),
            show="tree headings",
        )
        self.tree.heading("#0", text="Item")
        self.tree.heading("value", text="Value")
        self.tree.column("#0", width=420)
        self.tree.column("value", width=520)
        self.tree.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def add_detail_text(self, parent, row, columnspan):
        frame = ttk.Frame(parent)
        frame.grid(
            row=row,
            column=0,
            columnspan=columnspan,
            sticky="ew",
            pady=(6, 0),
        )
        text = tk.Text(
            frame,
            height=3,
            wrap="word",
            state="disabled",
            relief="solid",
            borderwidth=1,
        )
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)
        text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        frame.columnconfigure(0, weight=1)
        return text

    @staticmethod
    def set_detail_text(widget, text):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", str(text or ""))
        widget.configure(state="disabled")

    def refresh(self):
        try:
            self.status = self.client.request(
                {
                    "cmd": "system/io/status",
                    "raw": self.raw_var.get(),
                }
            )
            self.update_view()
        except Exception as exc:
            messagebox.showerror("IO Control Panel", str(exc))

    def update_gui(self):
        connected, error, status = self.client.get_snapshot()
        self.connected = connected
        if connected:
            self.status_var.set("Connected")
        else:
            self.status_var.set(f"Disconnected: {error}" if error else "Disconnected")

        if status:
            self.status = status
            self.update_command_authority(status.get("command_authority", {}))
            self.update_view()
        self.root.after(GUI_PERIOD_MS, self.update_gui)

    def update_view(self):
        devices = self.status.get("devices", [])
        device_ids = [device.get("id", "") for device in devices]
        self.device_combo["values"] = device_ids
        self.param_device_combo["values"] = device_ids
        self.ap_device_combo["values"] = device_ids
        self.iol_device_combo["values"] = device_ids
        if device_ids and self.device_var.get() not in device_ids:
            self.device_var.set(device_ids[0])

        selected = self.selected_device()
        output_slots = self.digital_output_slots(selected)
        self.slot_combo["values"] = output_slots
        if output_slots and self.slot_var.get() not in output_slots:
            self.slot_var.set(output_slots[0])

        open_paths = self.open_tree_paths()
        self.tree.delete(*self.tree.get_children())
        for device in devices:
            self.add_device(device)
        self.restore_open_tree_paths(open_paths)

    def add_device(self, device):
        device_id = self.tree.insert(
            "",
            "end",
            text=f"{device.get('id')} slave {device.get('slave_index')}",
            values=(f"{device.get('profile')} in={device.get('input_bytes')} out={device.get('output_bytes')}",),
            open=True,
        )
        self.tree.insert(
            device_id,
            "end",
            text="module 0 esi",
            values=("CPX-AP-I-EC",),
            open=True,
        )
        for module in device.get("modules", []):
            module_id = self.tree.insert(
                device_id,
                "end",
                text=f"module {module.get('slot')} {module.get('type')}",
                values=(self.module_display_name(module),),
                open=True,
            )
            for direction in ("inputs", "outputs"):
                values = module.get(direction, {})
                for key, value in values.items():
                    item_id = self.tree.insert(
                        module_id,
                        "end",
                        text=f"{direction}.{key}",
                        values=(self.tree_value_text(value),),
                    )
                    self.add_tree_value(
                        item_id,
                        value,
                    )
        if "input_image" in device:
            self.tree.insert(device_id, "end", text="input_image", values=(device["input_image"],))
            self.tree.insert(device_id, "end", text="output_image", values=(device["output_image"],))

    @staticmethod
    def module_display_name(module):
        return module.get("name") or module.get("raw") or module.get("type") or ""

    def add_tree_value(self, parent_id, value):
        if isinstance(value, dict):
            for key, child in value.items():
                child_id = self.tree.insert(
                    parent_id,
                    "end",
                    text=str(key),
                    values=(self.tree_value_text(child),),
                )
                self.add_tree_value(child_id, child)
            return
        if isinstance(value, list):
            for index, child in enumerate(value):
                label = self.tree_list_label(child, index)
                child_id = self.tree.insert(
                    parent_id,
                    "end",
                    text=label,
                    values=(self.tree_value_text(child),),
                )
                self.add_tree_value(child_id, child)

    def open_tree_paths(self):
        paths = set()
        for item_id in self.tree.get_children(""):
            self.collect_open_tree_paths(item_id, (), paths)
        return paths

    def collect_open_tree_paths(self, item_id, parent_path, paths):
        path = (*parent_path, self.tree.item(item_id, "text"))
        if self.tree.item(item_id, "open"):
            paths.add(path)
        for child_id in self.tree.get_children(item_id):
            self.collect_open_tree_paths(child_id, path, paths)

    def restore_open_tree_paths(self, open_paths):
        for item_id in self.tree.get_children(""):
            self.restore_open_tree_path(item_id, (), open_paths)

    def restore_open_tree_path(self, item_id, parent_path, open_paths):
        path = (*parent_path, self.tree.item(item_id, "text"))
        if path in open_paths:
            self.tree.item(item_id, open=True)
        for child_id in self.tree.get_children(item_id):
            self.restore_open_tree_path(child_id, path, open_paths)

    @staticmethod
    def tree_list_label(value, index):
        if isinstance(value, dict) and "port" in value:
            return f"port {value.get('port')}"
        return str(index)

    @staticmethod
    def tree_value_text(value):
        if isinstance(value, dict):
            return ""
        if isinstance(value, list):
            return f"{len(value)} items"
        return str(value)

    def selected_device(self):
        if self.status is None:
            return None
        selected_id = self.device_var.get()
        for device in self.status.get("devices", []):
            if device.get("id") == selected_id:
                return device
        return None

    @staticmethod
    def digital_output_slots(device):
        if not device:
            return []
        return [
            str(module.get("slot"))
            for module in device.get("modules", [])
            if int(module.get("digital_outputs", 0)) > 0
        ]

    def apply_digital_output(self):
        try:
            self.require_command_authority()
            response = self.client.request(
                {
                    "cmd": "system/io/output_write",
                    "io": self.device_var.get(),
                    "slot": int(self.slot_var.get()),
                    "kind": "digital",
                    "channel": int(self.channel_var.get()),
                    "value": self.output_value_var.get(),
                    "raw": self.raw_var.get(),
                },
                expected_type="system/io/output_write",
            )
            if response.get("type") == "command_rejected":
                raise RuntimeError(response.get("message", "command rejected"))
        except Exception as exc:
            messagebox.showerror("IO Control Panel", str(exc))

    def read_parameter(self):
        try:
            response = self.client.request(
                self.parameter_message("system/io/param_read"),
                expected_type="system/io/param_read",
            )
            self.show_parameter_response(response)
        except Exception as exc:
            messagebox.showerror("IO Control Panel", str(exc))

    def write_parameter(self):
        try:
            self.require_command_authority()
            message = self.parameter_message("system/io/param_write")
            message["value"] = self.param_value_var.get()
            response = self.client.request(
                message,
                expected_type="system/io/param_write",
            )
            self.show_parameter_response(response)
        except Exception as exc:
            messagebox.showerror("IO Control Panel", str(exc))

    def parameter_message(self, command):
        message = {
            "cmd": command,
            "io": self.device_var.get(),
            "index": self.param_index_var.get(),
            "subindex": self.param_subindex_var.get(),
            "data_type": self.param_type_var.get(),
        }
        length = self.param_length_from_type()
        if length:
            message["length"] = length
        return message

    def show_parameter_response(self, response):
        if response.get("type") == "command_rejected" or not response.get("ok", False):
            message = response.get("message", response.get("error", "command failed"))
            self.param_result_var.set(f"Error: {message}")
            return
        text = f"Value={response.get('value')}"
        if response.get("hex") is not None:
            text = f"{text} ({response.get('hex')})"
        self.param_result_var.set(text)

    def load_ec_catalog(self):
        try:
            response = self.client.request(
                {
                    "cmd": "system/io/ethercat/param_catalog",
                    "io": self.device_var.get(),
                },
                expected_type="system/io/ethercat/param_catalog",
            )
            if not response.get("ok", False):
                raise RuntimeError(response.get("error", "catalog request failed"))
            self.ec_catalog_items = self.ec_catalog_entries(response)
            labels = sorted(self.ec_catalog_items)
            self.ec_catalog_combo["values"] = labels
            if labels:
                self.ec_catalog_var.set(labels[0])
                self.on_ec_catalog_selected()
            self.param_result_var.set(f"Catalog loaded: {len(labels)} items")
        except Exception as exc:
            messagebox.showerror("IO Control Panel", str(exc))

    def on_ec_catalog_selected(self, _event=None):
        item = self.ec_catalog_items.get(self.ec_catalog_var.get())
        if not item:
            return
        self.param_index_var.set(item["index"])
        self.param_subindex_var.set(item["subindex"])
        self.param_type_var.set(item["data_type"])
        if item.get("length"):
            self.param_length_var.set(str(item["length"]))
        self.set_detail_text(self.ec_catalog_detail_text, item.get("detail", ""))

    def ec_catalog_entries(self, response):
        entries = {}
        for obj in response.get("objects", []):
            subitems = obj.get("subitems", [])
            if subitems:
                for subitem in subitems:
                    entry = {
                        "index": obj.get("index_hex", f"0x{int(obj.get('index', 0)):04X}"),
                        "subindex": f"0x{int(subitem.get('subindex', 0)):02X}",
                        "data_type": self.catalog_data_type(
                            subitem.get("data_type"),
                            subitem.get("bit_size"),
                        ),
                        "length": self.catalog_data_length(
                            subitem.get("data_type"),
                            subitem.get("bit_size"),
                        ),
                        "access": subitem.get("access", ""),
                        "detail": (
                            f"{obj.get('name', '')}.{subitem.get('name', '')} "
                            f"type={subitem.get('data_type', '')} "
                            f"access={subitem.get('access', '')}"
                        ),
                    }
                    label = (
                        f"{entry['index']}:{entry['subindex']} "
                        f"{self.short_catalog_name(subitem.get('name') or obj.get('name'))}"
                    )
                    entries[label] = entry
                continue

            entry = {
                "index": obj.get("index_hex", f"0x{int(obj.get('index', 0)):04X}"),
                "subindex": "0x00",
                "data_type": self.catalog_data_type(
                    obj.get("data_type"),
                    obj.get("bit_size"),
                ),
                "length": self.catalog_data_length(
                    obj.get("data_type"),
                    obj.get("bit_size"),
                ),
                "access": obj.get("access", ""),
                "detail": (
                    f"{obj.get('name', '')} "
                    f"type={obj.get('data_type', '')} "
                    f"access={obj.get('access', '')}"
                ),
            }
            label = f"{entry['index']}:0x00 {self.short_catalog_name(obj.get('name'))}"
            entries[label] = entry
        return entries

    def read_ap_parameter(self):
        try:
            response = self.client.request(
                self.ap_parameter_message("system/io/ap/param_read"),
                expected_type="system/io/ap/param_read",
            )
            self.show_ap_parameter_response(response)
        except Exception as exc:
            messagebox.showerror("IO Control Panel", str(exc))

    def write_ap_parameter(self):
        try:
            self.require_command_authority()
            message = self.ap_parameter_message("system/io/ap/param_write")
            message["value"] = self.ap_value_var.get()
            response = self.client.request(
                message,
                expected_type="system/io/ap/param_write",
            )
            self.show_ap_parameter_response(response)
        except Exception as exc:
            messagebox.showerror("IO Control Panel", str(exc))

    def ap_parameter_message(self, command):
        message = {
            "cmd": command,
            "io": self.device_var.get(),
            "module": self.ap_module_var.get(),
            "parameter_id": self.ap_parameter_id_var.get(),
            "instance": self.ap_instance_var.get(),
            "data_type": self.ap_type_var.get(),
        }
        if self.ap_length_var.get().strip():
            message["length"] = self.ap_length_var.get()
        return message

    def show_ap_parameter_response(self, response):
        if response.get("type") == "command_rejected" or not response.get("ok", False):
            message = response.get("message", response.get("error", "command failed"))
            self.ap_result_var.set(f"Error: {message}")
            return
        text = (
            f"Status={response.get('status')} "
            f"Length={response.get('length')} "
            f"Value={self.format_ap_value(response.get('value'))}"
        )
        if response.get("data"):
            text = f"{text} Data=0x{response.get('data')}"
        self.ap_result_var.set(text)

    def read_iol_parameter(self):
        try:
            response = self.client.request(
                self.iol_parameter_message("system/io/iol/param_read"),
                expected_type="system/io/iol/param_read",
            )
            self.show_iol_parameter_response(response)
        except Exception as exc:
            messagebox.showerror("IO Control Panel", str(exc))

    def write_iol_parameter(self):
        try:
            self.require_command_authority()
            message = self.iol_parameter_message("system/io/iol/param_write")
            message["value"] = self.iol_value_var.get()
            response = self.client.request(
                message,
                expected_type="system/io/iol/param_write",
            )
            self.show_iol_parameter_response(response)
        except Exception as exc:
            messagebox.showerror("IO Control Panel", str(exc))

    def iol_parameter_message(self, command):
        message = {
            "cmd": command,
            "io": self.device_var.get(),
            "module": self.iol_module_var.get(),
            "port": self.iol_port_var.get(),
            "index": self.iol_index_var.get(),
            "subindex": self.iol_subindex_var.get(),
            "data_type": self.iol_type_var.get(),
        }
        if self.iol_length_var.get().strip():
            message["length"] = self.iol_length_var.get()
        return message

    def show_iol_parameter_response(self, response):
        if response.get("type") == "command_rejected" or not response.get("ok", False):
            message = response.get("message", response.get("error", "command failed"))
            self.iol_result_var.set(f"Error: {message}")
            return
        text = (
            f"Status={response.get('status')} "
            f"Length={response.get('length')} "
            f"Value={self.format_ap_value(response.get('value'))}"
        )
        if response.get("data"):
            text = f"{text} Data=0x{response.get('data')}"
        self.iol_result_var.set(text)

    def load_iol_catalog(self):
        try:
            response = self.client.request(
                {
                    "cmd": "system/io/iol/param_catalog",
                    "io": self.device_var.get(),
                    "module": self.iol_module_var.get(),
                    "port": self.iol_port_var.get(),
                },
                expected_type="system/io/iol/param_catalog",
            )
            if not response.get("ok", False):
                raise RuntimeError(response.get("error", "catalog request failed"))
            self.iol_catalog_items = self.iol_catalog_entries(response)
            labels = sorted(self.iol_catalog_items)
            self.iol_catalog_combo["values"] = labels
            if labels:
                self.iol_catalog_var.set(labels[0])
                self.on_iol_catalog_selected()
            self.iol_result_var.set(
                "Catalog loaded: "
                f"module={self.iol_module_var.get()} "
                f"port={self.iol_port_var.get()} "
                f"items={len(labels)}"
            )
        except Exception as exc:
            messagebox.showerror("IO Control Panel", str(exc))

    def on_iol_catalog_selected(self, _event=None):
        item = self.iol_catalog_items.get(self.iol_catalog_var.get())
        if not item:
            return
        self.iol_module_var.set(str(item["module"]))
        self.iol_port_var.set(str(item["port"]))
        self.iol_index_var.set(item["index"])
        self.iol_subindex_var.set(item["subindex"])
        self.iol_type_var.set(item["data_type"])
        if item.get("length"):
            self.iol_length_var.set(str(item["length"]))
        self.set_detail_text(self.iol_catalog_detail_text, item.get("detail", ""))

    def iol_catalog_entries(self, response):
        entries = {}
        for module in response.get("modules", []):
            module_number = int(module.get("module", 0))
            for device in module.get("devices", []):
                port = int(device.get("port", 0))
                device_name = device.get("device_name", "")
                for variable in device.get("variables", []):
                    subindices = variable.get("subindices", [])
                    if subindices:
                        for subitem in subindices:
                            entry = self.iol_catalog_entry(
                                module_number,
                                port,
                                variable,
                                int(subitem.get("subindex", 0)),
                                device_name,
                            )
                            label = self.iol_catalog_label(
                                entry,
                                variable,
                                device_name,
                            )
                            entries[label] = entry
                        continue

                    entry = self.iol_catalog_entry(
                        module_number,
                        port,
                        variable,
                        0,
                        device_name,
                    )
                    label = self.iol_catalog_label(entry, variable, device_name)
                    entries[label] = entry
        return entries

    def iol_catalog_entry(self, module_number, port, variable, subindex, device_name):
        bit_length = int(variable.get("bit_length") or 0)
        return {
            "module": module_number,
            "port": port,
            "index": variable.get("index_hex", f"0x{int(variable.get('index', 0)):04X}"),
            "subindex": f"0x{subindex:02X}",
            "data_type": self.catalog_data_type(
                variable.get("data_type"),
                bit_length,
            ),
            "length": self.bytes_from_bits(bit_length),
            "access": variable.get("access", ""),
            "detail": (
                f"{variable.get('name', '')} "
                f"device={device_name} "
                f"type={variable.get('data_type', '')} "
                f"bits={bit_length} "
                f"access={variable.get('access', '')}"
            ),
        }

    @staticmethod
    def iol_catalog_label(entry, variable, device_name):
        return (
            f"M{entry['module']} P{entry['port']} "
            f"{entry['index']}:{entry['subindex']} "
            f"{IOControlPanel.short_catalog_name(variable.get('name'))}"
        )

    def on_ap_type_changed(self, _event=None):
        length = AP_TYPE_LENGTHS.get(self.ap_type_var.get())
        if length is not None:
            self.ap_length_var.set(length)

    def on_iol_type_changed(self, _event=None):
        length = AP_TYPE_LENGTHS.get(self.iol_type_var.get())
        if length is not None:
            self.iol_length_var.set(length)

    def param_length_from_type(self):
        if self.param_type_var.get().strip().lower() not in {"char", "string"}:
            return ""
        return self.param_length_var.get().strip()

    @staticmethod
    def format_ap_value(value):
        if isinstance(value, int):
            return f"{value} (0x{value:X})"
        return value

    @staticmethod
    def catalog_data_type(data_type, bit_length=None):
        # TECH_DEBT[TD-007]: Axis Diagnosis contains the same conversion policy.
        # Consolidate this when the IO panel is split into smaller modules.
        text = str(data_type or "").strip().lower()
        bit_length = int(bit_length or 0)
        if text.startswith("string("):
            return "string"
        if text.startswith("array"):
            return "bytes"
        if IOControlPanel.is_unsigned_catalog_type(text):
            return IOControlPanel.unsigned_type_for_bits(bit_length)
        if IOControlPanel.is_signed_catalog_type(text):
            return IOControlPanel.signed_type_for_bits(bit_length)
        mapping = {
            "bool": "uint8",
            "booleant": "uint8",
            "boolean": "uint8",
            "byte": "uint8",
            "uint8": "uint8",
            "usint": "uint8",
            "integer8": "int8",
            "int8": "int8",
            "sint": "int8",
            "uint16": "uint16",
            "uint": "uint16",
            "uint16t": "uint16",
            "uintegert": "uint16",
            "int16": "int16",
            "integer16": "int16",
            "uint32": "uint32",
            "udint": "uint32",
            "uint32t": "uint32",
            "int32": "int32",
            "dint": "int32",
            "integer32": "int32",
            "float32": "float32",
            "real": "float32",
            "stringt": "string",
            "visible_string": "string",
            "char": "string",
            "recordt": "bytes",
            "arrayt": "bytes",
        }
        return mapping.get(text, "bytes")

    @staticmethod
    def catalog_data_length(data_type, bit_length=None):
        text = str(data_type or "").strip().lower()
        match = re.match(r"string\((\d+)\)", text)
        if match:
            return int(match.group(1))
        if text in {"stringt", "visible_string", "char"} and bit_length:
            return max(1, int(bit_length) // 8)
        return None

    @staticmethod
    def is_unsigned_catalog_type(text):
        if text in {"uintegert", "uint", "unsigned", "usint", "byte"}:
            return True
        return bool(re.match(r"^dt[0-9a-f]*en[0-9a-f]+$", text))

    @staticmethod
    def is_signed_catalog_type(text):
        return text in {"integert", "int", "signed", "sint", "integer"}

    @staticmethod
    def unsigned_type_for_bits(bit_length):
        if int(bit_length or 0) <= 8:
            return "uint8"
        if int(bit_length or 0) <= 16:
            return "uint16"
        if int(bit_length or 0) <= 32:
            return "uint32"
        return "bytes"

    @staticmethod
    def signed_type_for_bits(bit_length):
        if int(bit_length or 0) <= 8:
            return "int8"
        if int(bit_length or 0) <= 16:
            return "int16"
        if int(bit_length or 0) <= 32:
            return "int32"
        return "bytes"

    @staticmethod
    def bytes_from_bits(bit_length):
        bit_length = int(bit_length or 0)
        if bit_length <= 0:
            return ""
        return max(1, (bit_length + 7) // 8)

    @staticmethod
    def short_catalog_name(name, max_length=32):
        text = " ".join(str(name or "").split())
        if len(text) <= max_length:
            return text
        return f"{text[:max_length - 3]}..."

    def toggle_command_authority(self):
        try:
            authority = self.current_authority()
            if authority.get("owned_by_this_client", False):
                self.client.release_command_authority()
            else:
                self.client.request_command_authority()
        except Exception as exc:
            messagebox.showerror("IO Control Panel", str(exc))

    def require_command_authority(self):
        if self.current_authority().get("owned_by_this_client", False):
            return
        raise RuntimeError("Command authority is required for this write command.")

    def current_authority(self):
        if not self.status:
            return {}
        return self.status.get("command_authority", {})

    def update_command_authority(self, authority):
        owner = authority.get("owner", None)
        owned_by_this_client = bool(authority.get("owned_by_this_client", False))
        if owned_by_this_client:
            self.command_authority_var.set("Authority: owned by this panel")
            self.command_authority_button_var.set("Release Authority")
        elif owner is None:
            self.command_authority_var.set("Authority: available")
            self.command_authority_button_var.set("Request Authority")
        else:
            self.command_authority_var.set(f"Authority: held by client {owner}")
            self.command_authority_button_var.set("Request Authority")

    def close(self):
        self.client.stop()
        self.root.destroy()


def main():
    host, port = read_runtime_config()
    root = tk.Tk()
    IOControlPanel(root, MotionServerClient(host, port))
    root.mainloop()


if __name__ == "__main__":
    main()
