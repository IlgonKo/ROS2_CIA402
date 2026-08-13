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
        self.raw_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Disconnected")
        self.connected = False

        self.root.title("IO Control Panel")
        self.root.geometry("980x680")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.build_ui()
        self.client.start()
        self.update_gui()

    def build_ui(self):
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill="x")

        ttk.Button(top, text="Refresh", command=self.refresh).pack(side="left")
        ttk.Checkbutton(
            top,
            text="Raw Image",
            variable=self.raw_var,
            command=self.refresh,
        ).pack(side="left", padx=(8, 0))
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

        ttk.Label(command, text="Slot").grid(row=0, column=2, sticky="w")
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

        parameter = ttk.LabelFrame(self.root, text="SDO Parameter", padding=8)
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
        ttk.Label(parameter, textvariable=self.param_result_var).grid(
            row=1,
            column=0,
            columnspan=12,
            sticky="w",
            pady=(6, 0),
        )

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
            self.update_view()
        self.root.after(GUI_PERIOD_MS, self.update_gui)

    def update_view(self):
        devices = self.status.get("devices", [])
        device_ids = [device.get("id", "") for device in devices]
        self.device_combo["values"] = device_ids
        self.param_device_combo["values"] = device_ids
        if device_ids and self.device_var.get() not in device_ids:
            self.device_var.set(device_ids[0])

        selected = self.selected_device()
        output_slots = self.digital_output_slots(selected)
        self.slot_combo["values"] = output_slots
        if output_slots and self.slot_var.get() not in output_slots:
            self.slot_var.set(output_slots[0])

        self.tree.delete(*self.tree.get_children())
        for device in devices:
            self.add_device(device)

    def add_device(self, device):
        device_id = self.tree.insert(
            "",
            "end",
            text=f"{device.get('id')} slave {device.get('slave_index')}",
            values=(f"{device.get('profile')} in={device.get('input_bytes')} out={device.get('output_bytes')}",),
            open=True,
        )
        for module in device.get("modules", []):
            module_id = self.tree.insert(
                device_id,
                "end",
                text=f"slot {module.get('slot')} {module.get('type')}",
                values=(f"in@{module.get('input_offset')} out@{module.get('output_offset')}",),
                open=True,
            )
            for direction in ("inputs", "outputs"):
                values = module.get(direction, {})
                for key, value in values.items():
                    self.tree.insert(
                        module_id,
                        "end",
                        text=f"{direction}.{key}",
                        values=(str(value),),
                    )
        if "input_image" in device:
            self.tree.insert(device_id, "end", text="input_image", values=(device["input_image"],))
            self.tree.insert(device_id, "end", text="output_image", values=(device["output_image"],))

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
            response = self.client.command_with_authority(
                {
                    "cmd": "system/io/output_write",
                    "io": self.device_var.get(),
                    "slot": int(self.slot_var.get()),
                    "kind": "digital",
                    "channel": int(self.channel_var.get()),
                    "value": self.output_value_var.get(),
                    "raw": self.raw_var.get(),
                }
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
            message = self.parameter_message("system/io/param_write")
            message["value"] = self.param_value_var.get()
            response = self.client.command_with_authority(
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
