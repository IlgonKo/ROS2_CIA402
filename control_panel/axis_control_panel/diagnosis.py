"""Diagnosis and SDO helpers for Axis Control Panel."""

import re
import time
from tkinter import messagebox


PANEL_SDO_READ_DELAY = 1.0
PANEL_SDO_READ_PERIOD = 0.1


class DiagnosisMixin:
    def diagnosis_read(self):
        request = self.read_diagnosis_request(include_value=False)
        if request is None:
            return
        axis_index, index, subindex, data_type, length, _value = request
        self.diagnosis_result_var.set("Waiting for SDO read response...")
        self.try_send(
            lambda: self.client.send_param_read(
                axis_index,
                index,
                subindex,
                data_type,
                length,
            )
        )

    def diagnosis_write(self):
        request = self.read_diagnosis_request(include_value=True)
        if request is None:
            return
        axis_index, index, subindex, data_type, length, value = request
        self.diagnosis_result_var.set("Waiting for SDO write response...")
        if self.try_send(
            lambda: self.client.send_param_write(
                axis_index,
                index,
                subindex,
                data_type,
                value,
                length,
            )
        ):
            self.queue_panel_sdo_reads([
                (axis_index, index, subindex, data_type, length),
            ])

    def load_diagnosis_catalog(self):
        axis_index = self.selected_axis()
        self.diagnosis_result_var.set("Waiting for parameter catalog...")
        self.try_send(lambda: self.client.send_axis_param_catalog(axis_index))

    def process_axis_param_catalog(self):
        response = self.client.pop_axis_param_catalog()
        if not response:
            return
        if not response.get("ok", False):
            self.diagnosis_result_var.set(
                "Catalog load failed: "
                f"{response.get('error', 'unknown error')}"
            )
            return

        self.diagnosis_catalog_items = self.diagnosis_catalog_entries(response)
        labels = sorted(self.diagnosis_catalog_items)
        self.diagnosis_catalog_combo["values"] = labels
        if labels:
            self.diagnosis_catalog_var.set(labels[0])
            self.on_diagnosis_catalog_selected()
        self.diagnosis_result_var.set(
            "Catalog loaded: "
            f"axis={response.get('axis')} "
            f"profile={response.get('profile', '')} "
            f"items={len(labels)}"
        )

    def on_diagnosis_catalog_selected(self, _event=None):
        item = self.diagnosis_catalog_items.get(self.diagnosis_catalog_var.get())
        if not item:
            return
        self.diagnosis_index_var.set(item["index"])
        self.diagnosis_subindex_var.set(item["subindex"])
        self.diagnosis_type_var.set(item["data_type"])
        if item.get("length"):
            self.diagnosis_length_var.set(str(item["length"]))
        else:
            self.diagnosis_length_var.set("")
        self.set_diagnosis_catalog_detail(item.get("detail", ""))

    def diagnosis_catalog_entries(self, response):
        entries = {}
        for obj in response.get("objects", []):
            subitems = obj.get("subitems", [])
            if subitems:
                for subitem in subitems:
                    entry = self.diagnosis_catalog_entry(
                        obj,
                        subitem,
                        subitem.get("subindex", 0),
                    )
                    label = self.diagnosis_catalog_label(
                        entry,
                        subitem.get("name") or obj.get("name"),
                    )
                    entries[label] = entry
                continue

            entry = self.diagnosis_catalog_entry(obj, None, 0)
            label = self.diagnosis_catalog_label(entry, obj.get("name"))
            entries[label] = entry
        return entries

    def diagnosis_catalog_entry(self, obj, subitem, subindex):
        item = subitem or obj
        data_type = item.get("data_type")
        bit_size = item.get("bit_size")
        object_name = str(obj.get("name", ""))
        item_name = str(item.get("name", ""))
        return {
            "index": obj.get("index_hex", f"0x{int(obj.get('index', 0)):04X}"),
            "subindex": f"0x{int(subindex):02X}",
            "data_type": self.catalog_data_type(data_type, bit_size),
            "length": self.catalog_data_length(data_type, bit_size),
            "access": item.get("access", obj.get("access", "")),
            "detail": (
                f"{object_name}"
                f"{'.' + item_name if subitem else ''} "
                f"type={data_type or ''} "
                f"bits={bit_size or ''} "
                f"access={item.get('access', obj.get('access', ''))}"
            ),
        }

    @staticmethod
    def diagnosis_catalog_label(entry, name):
        return (
            f"{entry['index']}:{entry['subindex']} "
            f"{DiagnosisMixin.short_catalog_name(name)}"
        )

    def set_diagnosis_catalog_detail(self, text):
        widget = getattr(self, "diagnosis_catalog_detail_text", None)
        if widget is None:
            return
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def diagnosis_parameter_save(self):
        axis_index = self.selected_axis()
        self.diagnosis_result_var.set("Waiting for parameter save response...")
        self.try_send(lambda: self.client.send_param_save(axis_index))

    def axis_restart(self):
        axis_index = self.selected_axis()
        confirmed = messagebox.askyesno(
            "Restart Selected Axis",
            f"Restart Axis {axis_index} device?",
        )
        if not confirmed:
            return
        self.stop_tab_motion()
        self.diagnosis_result_var.set("Waiting for axis restart response...")
        self.try_send(lambda: self.client.send_axis_restart(axis_index))

    def server_reset(self):
        self.stop_tab_motion()
        self.diagnosis_result_var.set("Waiting for server reset response...")
        self.try_send(self.client.send_server_reset)

    def bus_reconnect(self):
        self.stop_tab_motion()
        self.diagnosis_result_var.set("Waiting for bus reconnect response...")
        self.try_send(self.client.send_bus_reconnect)

    def server_restart(self):
        confirmed = messagebox.askyesno(
            "Restart Motion Server",
            "Restart Motion Server process?",
        )
        if not confirmed:
            return
        self.stop_tab_motion()
        self.diagnosis_result_var.set("Waiting for server restart response...")
        self.try_send(self.client.send_server_restart)

    def read_diagnosis_request(self, include_value):
        data_type = self.diagnosis_type_var.get().strip().lower()
        if data_type not in {
            "uint8",
            "int8",
            "uint16",
            "int16",
            "int32",
            "uint32",
            "udint",
            "float32",
            "string",
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

        length = None
        if data_type == "string":
            raw_length = self.diagnosis_length_var.get().strip()
            try:
                length = int(raw_length, 0)
            except ValueError:
                messagebox.showerror(
                    "Invalid Input",
                    "String SDO access requires a valid length.",
                )
                return None

        value = None
        if include_value:
            raw_value = self.diagnosis_value_var.get().strip()
            try:
                if data_type == "float32":
                    value = float(raw_value)
                elif data_type == "string":
                    value = raw_value
                else:
                    int(raw_value, 0)
                    value = raw_value
            except ValueError:
                messagebox.showerror(
                    "Invalid Input",
                    "Value must match the selected SDO data type.",
                )
                return None

        return self.selected_axis(), index, subindex, data_type, length, value

    @staticmethod
    def catalog_data_type(data_type, bit_length=None):
        # TECH_DEBT[TD-007]: IO Control Panel contains a parallel catalog type
        # converter. Move both panels to a shared catalog utility.
        text = str(data_type or "").strip().lower()
        bit_length = int(bit_length or 0)
        if text.startswith("string("):
            return "string"
        if text in {"stringt", "visible_string", "visible-string", "char"}:
            return "string"
        if text.startswith("array"):
            return "string" if "char" in text else "uint32"
        if DiagnosisMixin.is_unsigned_catalog_type(text):
            return DiagnosisMixin.unsigned_type_for_bits(bit_length)
        if DiagnosisMixin.is_signed_catalog_type(text):
            return DiagnosisMixin.signed_type_for_bits(bit_length)
        mapping = {
            "bool": "uint8",
            "booleant": "uint8",
            "boolean": "uint8",
            "byte": "uint8",
            "usint": "uint8",
            "uint8": "uint8",
            "sint": "int8",
            "int8": "int8",
            "uint16": "uint16",
            "uint32": "uint32",
            "udint": "uint32",
            "dint": "int32",
            "int32": "int32",
            "real": "float32",
            "float32": "float32",
        }
        return mapping.get(text, "uint32")

    @staticmethod
    def catalog_data_length(data_type, bit_length=None):
        text = str(data_type or "").strip().lower()
        match = re.match(r"string\((\d+)\)", text)
        if match:
            return int(match.group(1))
        if text in {"stringt", "visible_string", "visible-string", "char"}:
            return DiagnosisMixin.bytes_from_bits(bit_length)
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
        return "uint32"

    @staticmethod
    def signed_type_for_bits(bit_length):
        if int(bit_length or 0) <= 8:
            return "int8"
        if int(bit_length or 0) <= 16:
            return "int16"
        return "int32"

    @staticmethod
    def bytes_from_bits(bit_length):
        bit_length = int(bit_length or 0)
        if bit_length <= 0:
            return None
        return max(1, (bit_length + 7) // 8)

    @staticmethod
    def short_catalog_name(name, max_length=42):
        text = " ".join(str(name or "").split())
        if len(text) <= max_length:
            return text
        return f"{text[:max_length - 3]}..."

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

        task = self.panel_sdo_read_queue.pop(0)
        axis_index, index, subindex, data_type = task[:4]
        length = task[4] if len(task) > 4 else None
        try:
            self.client.send_param_read(axis_index, index, subindex, data_type, length)
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
