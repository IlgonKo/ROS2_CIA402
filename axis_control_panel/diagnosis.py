"""Diagnosis and SDO helpers for Axis Control Panel."""

import time
from tkinter import messagebox


PANEL_SDO_READ_DELAY = 1.0
PANEL_SDO_READ_PERIOD = 0.1


class DiagnosisMixin:
    def diagnosis_read(self):
        request = self.read_diagnosis_request(include_value=False)
        if request is None:
            return
        axis_index, index, subindex, data_type, _value = request
        self.diagnosis_result_var.set("Waiting for SDO read response...")
        self.try_send(
            lambda: self.client.send_param_read(
                axis_index,
                index,
                subindex,
                data_type,
            )
        )

    def diagnosis_write(self):
        request = self.read_diagnosis_request(include_value=True)
        if request is None:
            return
        axis_index, index, subindex, data_type, value = request
        self.diagnosis_result_var.set("Waiting for SDO write response...")
        if self.try_send(
            lambda: self.client.send_param_write(
                axis_index,
                index,
                subindex,
                data_type,
                value,
            )
        ):
            self.queue_panel_sdo_reads([
                (axis_index, index, subindex, data_type),
            ])

    def diagnosis_parameter_save(self):
        axis_index = self.selected_axis()
        self.diagnosis_result_var.set("Waiting for parameter save response...")
        self.try_send(lambda: self.client.send_param_save(axis_index))

    def read_diagnosis_request(self, include_value):
        data_type = self.diagnosis_type_var.get().strip().lower()
        if data_type not in {
            "uint8",
            "int8",
            "uint16",
            "int32",
            "uint32",
            "udint",
            "float32",
        }:
            messagebox.showerror("Invalid Input", "Unsupported SDO data type.")
            return None

        index = self.diagnosis_index_var.get().strip()
        subindex = self.diagnosis_subindex_var.get().strip()
        try:
            int(index, 0)
            int(subindex, 0)
        except ValueError:
            messagebox.showerror(
                "Invalid Input",
                "Index and subindex must be decimal or hex values.",
            )
            return None

        value = None
        if include_value:
            raw_value = self.diagnosis_value_var.get().strip()
            try:
                if data_type == "float32":
                    value = float(raw_value)
                else:
                    int(raw_value, 0)
                    value = raw_value
            except ValueError:
                messagebox.showerror(
                    "Invalid Input",
                    "Value must match the selected SDO data type.",
                )
                return None

        return self.selected_axis(), index, subindex, data_type, value

    def queue_panel_sdo_reads(self, tasks):
        with self.client.lock:
            self._queue_panel_sdo_reads_locked(tasks)

    def _queue_panel_sdo_reads_locked(self, tasks):
        self.panel_sdo_read_queue = list(tasks) + list(self.panel_sdo_read_queue)
        self.panel_sdo_read_next_time = time.monotonic() + PANEL_SDO_READ_PERIOD

    @staticmethod

    def _format_sdo_index(value):
        return f"0x{int(value):04X}"

    @staticmethod

    def _format_sdo_subindex(value):
        return f"0x{int(value):02X}"

    def reset_panel_sdo_read_queue(self):
        self.panel_sdo_read_queue = []
        self.panel_sdo_read_next_time = 0.0
        self.panel_sdo_read_connected = False

    def start_panel_sdo_read_queue(self):
        if not self.auto_sdo_reads:
            self.reset_panel_sdo_read_queue()
            return

        self.panel_sdo_read_queue = []
        for axis_index in range(self.axis_count):
            self.panel_sdo_read_queue.extend([
                (axis_index, "0x2145", "0x0C", "uint32"),
                (axis_index, "0x6061", "0x00", "int8"),
                (axis_index, "0x607D", "0x01", "int32"),
                (axis_index, "0x607D", "0x02", "int32"),
                (axis_index, "0x6081", "0x00", "uint32"),
                (axis_index, "0x6083", "0x00", "uint32"),
                (axis_index, "0x6084", "0x00", "uint32"),
                (axis_index, "0x60A4", "0x01", "uint32"),
                (axis_index, "0x607F", "0x00", "uint32"),
                (axis_index, "0x2183", "0x0C", "float32"),
                (axis_index, "0x60C5", "0x00", "uint32"),
                (axis_index, "0x60C6", "0x00", "uint32"),
            ])
        self.panel_sdo_read_next_time = time.monotonic() + PANEL_SDO_READ_DELAY
        self.panel_sdo_read_connected = True

    def process_panel_sdo_read_queue(self, connected):
        if not connected:
            if self.panel_sdo_read_connected:
                self.reset_panel_sdo_read_queue()
            return

        if not self.panel_sdo_read_queue:
            return

        now = time.monotonic()
        if now < self.panel_sdo_read_next_time:
            return

        axis_index, index, subindex, data_type = self.panel_sdo_read_queue.pop(0)
        try:
            self.client.send_param_read(axis_index, index, subindex, data_type)
        except Exception as exc:
            self.diagnosis_result_var.set(
                "Panel SDO auto-read failed: "
                f"axis={axis_index} index={index}:{subindex} ({exc})"
            )
        finally:
            self.panel_sdo_read_next_time = now + PANEL_SDO_READ_PERIOD

    def _format_error_code(self, diagnostics):
        text = diagnostics.get("error_code_text", None)
        if isinstance(text, str) and text:
            return text

        value = diagnostics.get("error_code", None)
        if isinstance(value, int):
            if value == 0:
                return "No error"
            return f"Error {value}"
        if value is None:
            return "n/a"
        return "read fail"
