"""Statusword display helpers for Axis Control Panel."""


STATUSWORD_BITS = [
    (0, "Ready"),
    (1, "Switched"),
    (2, "Op En"),
    (3, "Fault"),
    (4, "Volt En"),
    (5, "Quick Stop"),
    (6, "SOD"),
    (7, "Warning"),
    (8, "Moving"),
    (9, "Remote"),
    (10, "Reached"),
    (11, "Limit"),
    (12, "OMS 12"),
    (13, "OMS 13"),
    (14, "Manuf 14"),
    (15, "Referenced"),
]


class StatuswordMixin:
    def update_statusword_lamps(self, statusword):
        for lamp, (bit, _label) in zip(self.statusword_lamps, STATUSWORD_BITS):
            is_on = bool(statusword & (1 << bit))
            if not is_on:
                lamp.configure(bg="#3a3a3a", fg="#d0d0d0")
            elif bit == 3:
                lamp.configure(bg="#c0392b", fg="#ffffff")
            elif bit == 7:
                lamp.configure(bg="#d68910", fg="#ffffff")
            else:
                lamp.configure(bg="#1e8449", fg="#ffffff")

    def statusword_state_text(self, statusword):
        masked = statusword & 0x006F
        if statusword & 0x0008:
            return "Fault"
        if masked == 0x0027:
            return "Op Enabled"
        if masked == 0x0023:
            return "Switched On"
        if masked == 0x0021:
            return "Ready"
        if masked == 0x0040:
            return "Switch Disabled"
        if masked == 0x0000:
            return "Not Ready"
        return "State Changed"

    def update_axis_enable_button(self, statusword):
        self.selected_axis_operation_enabled = bool(int(statusword) & 0x0004)
        self.axis_enable_button_var.set(
            "Disable" if self.selected_axis_operation_enabled else "Enable"
        )
