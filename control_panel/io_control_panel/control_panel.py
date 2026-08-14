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
        self.param_value_var = tk.StringVar(value="0")
        self.param_result_var = tk.StringVar(value="")
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

        parameter = ttk.LabelFrame(self.root, text="EtherCAT Parameter", padding=8)
        parameter.pack(fill="x", padx=8, pady=(0, 8))

        ttk.Label(parameter, text="I/O").grid(row=0, column=0, sticky="w")
        self.param_device_combo = ttk.Combobox(
            parameter,
            textvariable=self.device_var,
            width=12,
            state="readonly",
        )
        self.param_device_combo.grid(row=0, column=1, padx=4)

        ttk.Label(parameter, text="Index").grid(row=0, column=2, sticky="w")
        ttk.Entry(parameter, textvariable=self.param_index_var, width=10).grid(
            row=0,
            column=3,
            padx=4,
        )

        ttk.Label(parameter, text="Sub").grid(row=0, column=4, sticky="w")
        ttk.Entry(parameter, textvariable=self.param_subindex_var, width=8).grid(
            row=0,
            column=5,
            padx=4,
        )

        ttk.Label(parameter, text="Type").grid(row=0, column=6, sticky="w")
        ttk.Combobox(
            parameter,
            textvariable=self.param_type_var,
            values=("uint8", "int8", "uint16", "int32", "uint32", "float32"),
            width=9,
            state="readonly",
        ).grid(row=0, column=7, padx=4)

        ttk.Label(parameter, text="Value").grid(row=0, column=8, sticky="w")
        ttk.Entry(parameter, textvariable=self.param_value_var, width=12).grid(
            row=0,
            column=9,
            padx=4,
        )

        ttk.Button(parameter, text="Read", command=self.read_parameter).grid(
            row=0,
            column=10,
            padx=(8, 0),
        )
        ttk.Button(parameter, text="Write", command=self.write_parameter).grid(
            row=0,
            column=11,
            padx=4,
        )
        ttk.Entry(
            parameter,
            textvariable=self.param_result_var,
            state="readonly",
        ).grid(
            row=1,
            column=0,
            columnspan=12,
            sticky="ew",
            pady=(6, 0),
        )
        parameter.columnconfigure(11, weight=1)

        ap_parameter = ttk.LabelFrame(self.root, text="AP Parameter", padding=8)
        ap_parameter.pack(fill="x", padx=8, pady=(0, 8))

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

        iol_parameter = ttk.LabelFrame(self.root, text="IOL Parameter", padding=8)
        iol_parameter.pack(fill="x", padx=8, pady=(0, 8))

        ttk.Label(iol_parameter, text="I/O").grid(row=0, column=0, sticky="w")
        self.iol_device_combo = ttk.Combobox(
            iol_parameter,
            textvariable=self.device_var,
            width=12,
            state="readonly",
        )
        self.iol_device_combo.grid(row=0, column=1, padx=4)

        ttk.Label(iol_parameter, text="Module").grid(row=0, column=2, sticky="w")
        ttk.Entry(iol_parameter, textvariable=self.iol_module_var, width=8).grid(
            row=0,
            column=3,
            padx=4,
        )

        ttk.Label(iol_parameter, text="Port").grid(row=0, column=4, sticky="w")
        ttk.Entry(iol_parameter, textvariable=self.iol_port_var, width=8).grid(
            row=0,
            column=5,
            padx=4,
        )

        ttk.Label(iol_parameter, text="Index").grid(row=0, column=6, sticky="w")
        ttk.Entry(iol_parameter, textvariable=self.iol_index_var, width=10).grid(
            row=0,
            column=7,
            padx=4,
        )

        ttk.Label(iol_parameter, text="Sub").grid(row=0, column=8, sticky="w")
        ttk.Entry(iol_parameter, textvariable=self.iol_subindex_var, width=8).grid(
            row=0,
            column=9,
            padx=4,
        )

        ttk.Label(iol_parameter, text="Length").grid(row=1, column=0, sticky="w")
        ttk.Entry(iol_parameter, textvariable=self.iol_length_var, width=8).grid(
            row=1,
            column=1,
            padx=4,
            pady=(6, 0),
        )

        ttk.Label(iol_parameter, text="Type").grid(row=1, column=2, sticky="w", pady=(6, 0))
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
        self.iol_type_combo.grid(row=1, column=3, padx=4, pady=(6, 0))
        self.iol_type_combo.bind("<<ComboboxSelected>>", self.on_iol_type_changed)

        ttk.Label(iol_parameter, text="Value").grid(row=1, column=4, sticky="w", pady=(6, 0))
        ttk.Entry(iol_parameter, textvariable=self.iol_value_var, width=18).grid(
            row=1,
            column=5,
            columnspan=2,
            sticky="w",
            padx=4,
            pady=(6, 0),
        )

        ttk.Button(iol_parameter, text="Read", command=self.read_iol_parameter).grid(
            row=1,
            column=7,
            padx=(8, 0),
            pady=(6, 0),
        )
        ttk.Button(iol_parameter, text="Write", command=self.write_iol_parameter).grid(
            row=1,
            column=8,
            padx=4,
            pady=(6, 0),
        )
        ttk.Entry(
            iol_parameter,
            textvariable=self.iol_result_var,
            state="readonly",
        ).grid(
            row=2,
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
            text="module 1 ESI",
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
        return {
            "cmd": command,
            "io": self.device_var.get(),
            "index": self.param_index_var.get(),
            "subindex": self.param_subindex_var.get(),
            "data_type": self.param_type_var.get(),
        }

    def show_parameter_response(self, response):
        if response.get("type") == "command_rejected" or not response.get("ok", False):
            message = response.get("message", response.get("error", "command failed"))
            self.param_result_var.set(f"Error: {message}")
            return
        text = f"Value={response.get('value')}"
        if response.get("hex") is not None:
            text = f"{text} ({response.get('hex')})"
        self.param_result_var.set(text)

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
                self.iol_parameter_message("system/io/iolink/isdu_read"),
                expected_type="system/io/iolink/isdu_read",
            )
            self.show_iol_parameter_response(response)
        except Exception as exc:
            messagebox.showerror("IO Control Panel", str(exc))

    def write_iol_parameter(self):
        try:
            self.require_command_authority()
            message = self.iol_parameter_message("system/io/iolink/isdu_write")
            message["value"] = self.iol_value_var.get()
            response = self.client.request(
                message,
                expected_type="system/io/iolink/isdu_write",
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

    def on_ap_type_changed(self, _event=None):
        length = AP_TYPE_LENGTHS.get(self.ap_type_var.get())
        if length is not None:
            self.ap_length_var.set(length)

    def on_iol_type_changed(self, _event=None):
        length = AP_TYPE_LENGTHS.get(self.iol_type_var.get())
        if length is not None:
            self.iol_length_var.set(length)

    @staticmethod
    def format_ap_value(value):
        if isinstance(value, int):
            return f"{value} (0x{value:X})"
        return value

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
