"""Single-axis UI builder for Axis Control Panel."""

import tkinter as tk
from tkinter import scrolledtext, ttk

from control_panel.axis_control_panel.statusword import STATUSWORD_BITS
from control_panel.axis_control_panel.trace import TraceCanvas


class SingleAxisViewBuilderMixin:
    def _build_ui(self):
        self._build_panel_layout()

        status_frame = ttk.LabelFrame(self.single_axis_area, text="Selected Axis Statusword")
        status_frame.pack(fill="x", pady=(0, 10))
        for index, (bit, label) in enumerate(STATUSWORD_BITS):
            lamp = tk.Label(
                status_frame,
                text=f"b{bit} {label}",
                width=11,
                bg="#3a3a3a",
                fg="#d0d0d0",
                relief="sunken",
                bd=1,
            )
            lamp.grid(
                row=index // 8,
                column=index % 8,
                padx=3,
                pady=3,
                sticky="ew",
            )
            status_frame.columnconfigure(index % 8, weight=1)
            self.statusword_lamps.append(lamp)

        self.mode_frame = ttk.LabelFrame(self.single_axis_area, text="Motion Mode")
        self.mode_frame.pack(fill="x", pady=(0, 10))
        ttk.Radiobutton(
            self.mode_frame,
            text="PP",
            value="pp",
            variable=self.motion_mode_var,
            command=self.apply_motion_mode,
        ).pack(side="left", padx=8, pady=5)
        self.pv_mode_button = ttk.Radiobutton(
            self.mode_frame,
            text="PV",
            value="pv",
            variable=self.motion_mode_var,
            command=self.apply_motion_mode,
        )
        self.pv_mode_button.pack(side="left", padx=8, pady=5)
        self.csp_mode_button = ttk.Radiobutton(
            self.mode_frame,
            text="CSP",
            value="csp",
            variable=self.motion_mode_var,
            command=self.apply_motion_mode,
        )
        self.csp_mode_button.pack(side="left", padx=8, pady=5)
        self.single_control_notebook = ttk.Notebook(self.single_axis_area)
        self.single_control_notebook.pack(fill="x", pady=(0, 10))

        motion_tab = ttk.Frame(self.single_control_notebook, padding=6)
        settings_tab = ttk.Frame(self.single_control_notebook, padding=6)
        limits_tab = ttk.Frame(self.single_control_notebook, padding=6)
        diagnosis_tab = ttk.Frame(self.single_control_notebook, padding=6)
        self.single_control_notebook.add(motion_tab, text="Motion")
        self.single_control_notebook.add(settings_tab, text="Settings")
        self.single_control_notebook.add(limits_tab, text="Limits")
        self.single_control_notebook.add(diagnosis_tab, text="Diagnosis")
        self.single_control_notebook.bind(
            "<<NotebookTabChanged>>",
            self.on_single_control_tab_changed,
        )

        detail = ttk.LabelFrame(motion_tab, text="Selected Axis Command / Feedback")
        detail.pack(fill="x")

        fields = [
            ("Selected Axis", self.selected_axis_label_var, "label"),
            ("Target Position mm", self.command_var, "entry"),
            ("Profile Velocity mm/s", self.profile_vars[0], "entry"),
            ("Active Target Position mm", self.target_var, "label"),
            ("Actual Position mm", self.actual_position_var, "label"),
            ("Actual Velocity mm/s", self.actual_velocity_var, "label"),
            ("Command Velocity mm/s", self.command_velocity_var, "label"),
            ("Statusword", self.statusword_var, "label"),
        ]
        for index, (label, var, kind) in enumerate(fields):
            row = index // 4
            column = (index % 4) * 2
            label_widget = ttk.Label(detail, text=label)
            self.motion_field_labels[label] = label_widget
            label_widget.grid(
                row=row,
                column=column,
                padx=5,
                pady=5,
                sticky="e",
            )
            if kind.startswith("entry"):
                entry = ttk.Entry(detail, textvariable=var, justify="right", width=14)
                self.motion_entry_widgets[label] = entry
                entry.bind(
                    "<KeyRelease>",
                    lambda _event, watched_var=var: self.mark_dirty(watched_var),
                )
                self.bind_entry_focus(entry, var)
                entry.grid(row=row, column=column + 1, padx=5, pady=5, sticky="ew")
            else:
                ttk.Label(detail, textvariable=var, anchor="e", width=16).grid(
                    row=row,
                    column=column + 1,
                    padx=5,
                    pady=5,
                    sticky="ew",
                )
            detail.columnconfigure(column + 1, weight=1)

        error_row = (len(fields) + 3) // 4
        ttk.Label(detail, text="Error").grid(
            row=error_row,
            column=0,
            padx=5,
            pady=5,
            sticky="e",
        )
        ttk.Label(
            detail,
            textvariable=self.error_code_var,
            anchor="w",
            wraplength=1050,
        ).grid(
            row=error_row,
            column=1,
            columnspan=7,
            padx=5,
            pady=5,
            sticky="ew",
        )
        detail.columnconfigure(1, weight=1)

        buttons = ttk.Frame(motion_tab)
        buttons.pack(fill="x", pady=(12, 8))
        ttk.Button(
            buttons,
            textvariable=self.axis_enable_button_var,
            command=self.toggle_axis_enable,
        ).pack(
            side="left",
            padx=4,
        )
        ttk.Button(buttons, text="Run", command=self.send_command).pack(
            side="left",
            padx=4,
        )
        ttk.Button(buttons, text="Stop", command=self.axis_stop).pack(
            side="left",
            padx=4,
        )
        ttk.Button(buttons, text="Homing", command=self.homing_start).pack(
            side="left",
            padx=4,
        )
        ttk.Button(buttons, text="Fault Reset", command=self.axis_fault_reset).pack(
            side="left",
            padx=4,
        )
        self.manual_controlword_frame = ttk.Frame(buttons)
        self.manual_controlword_frame.pack(side="left", padx=(12, 0))
        ttk.Label(self.manual_controlword_frame, text="Manual CW").pack(
            side="left",
            padx=(0, 4),
        )
        for label, value in [
            ("Shutdown", 0x0006),
            ("Switch On", 0x0007),
            ("Enable Op", 0x000F),
            ("Disable Voltage", 0x0000),
        ]:
            button = ttk.Button(
                self.manual_controlword_frame,
                text=label,
                command=lambda cw=value: self.send_manual_controlword(cw),
            )
            button.pack(side="left", padx=2)
            self.manual_controlword_buttons.append(button)

        jog = ttk.LabelFrame(motion_tab, text="Jog")
        jog.pack(fill="x", pady=(4, 10))
        ttk.Label(jog, text="Selected Axis").pack(side="left", padx=(8, 4), pady=6)
        ttk.Label(jog, textvariable=self.selected_axis_label_var, width=8).pack(
            side="left",
            padx=4,
            pady=6,
        )
        ttk.Label(jog, text="Speed").pack(side="left", padx=(12, 4), pady=6)
        ttk.Label(jog, text="slow").pack(side="left", padx=4, pady=6)
        jog_negative = ttk.Button(
            jog,
            text="Jog -",
        )
        jog_negative.pack(side="left", padx=4, pady=6)
        jog_negative.bind(
            "<ButtonPress-1>",
            lambda _event: self.jog_start("negative"),
        )
        jog_negative.bind("<ButtonRelease-1>", lambda _event: self.jog_stop())
        jog_negative.bind("<Leave>", lambda _event: self.jog_stop())

        jog_positive = ttk.Button(
            jog,
            text="Jog +",
        )
        jog_positive.pack(side="left", padx=4, pady=6)
        jog_positive.bind(
            "<ButtonPress-1>",
            lambda _event: self.jog_start("positive"),
        )
        jog_positive.bind("<ButtonRelease-1>", lambda _event: self.jog_stop())
        jog_positive.bind("<Leave>", lambda _event: self.jog_stop())

        repeat = ttk.LabelFrame(motion_tab, text="Repeat Motion")
        repeat.pack(fill="x", pady=(4, 10))
        ttk.Label(repeat, text="Selected Axis").grid(row=0, column=0, padx=5, pady=4)
        ttk.Label(repeat, textvariable=self.selected_axis_label_var).grid(
            row=0,
            column=1,
            padx=5,
            pady=4,
            sticky="w",
        )
        self.repeat_label_widgets["point_a"] = ttk.Label(repeat, text="Point A mm")
        self.repeat_label_widgets["point_a"].grid(row=0, column=2, padx=5, pady=4)
        entry = ttk.Entry(
            repeat,
            textvariable=self.repeat_point_a_var,
            justify="right",
            width=14,
        )
        self.bind_entry_focus(entry, self.repeat_point_a_var)
        entry.grid(row=0, column=3, padx=5, pady=4)
        self.repeat_label_widgets["point_b"] = ttk.Label(repeat, text="Point B mm")
        self.repeat_label_widgets["point_b"].grid(row=0, column=4, padx=5, pady=4)
        entry = ttk.Entry(
            repeat,
            textvariable=self.repeat_point_b_var,
            justify="right",
            width=14,
        )
        self.bind_entry_focus(entry, self.repeat_point_b_var)
        entry.grid(row=0, column=5, padx=5, pady=4)
        self.repeat_label_widgets["velocity"] = ttk.Label(repeat, text="Profile Velocity mm/s")
        self.repeat_label_widgets["velocity"].grid(
            row=0,
            column=6,
            padx=5,
            pady=4,
        )
        entry = ttk.Entry(
            repeat,
            textvariable=self.repeat_profile_velocity_var,
            justify="right",
            width=14,
        )
        self.bind_entry_focus(entry, self.repeat_profile_velocity_var)
        entry.grid(row=0, column=7, padx=5, pady=4)
        ttk.Label(repeat, text="Period (s)").grid(row=0, column=8, padx=5, pady=4)
        entry = ttk.Entry(
            repeat,
            textvariable=self.repeat_period_var,
            justify="right",
            width=10,
        )
        self.bind_entry_focus(entry, self.repeat_period_var)
        entry.grid(row=0, column=9, padx=5, pady=4)
        ttk.Button(repeat, text="Start Repeat", command=self.start_repeat).grid(
            row=0,
            column=10,
            padx=5,
            pady=4,
        )
        ttk.Button(repeat, text="Stop Repeat", command=self.stop_repeat).grid(
            row=0,
            column=11,
            padx=5,
            pady=4,
        )

        profile_frame = ttk.LabelFrame(settings_tab, text="Selected Axis PP Profile")
        profile_frame.pack(fill="x", pady=(0, 10))
        profile_fields = [
            ("Profile Velocity mm/s", self.profile_vars[0]),
            ("Profile Accel mm/s^2", self.profile_vars[1]),
            ("Profile Decel mm/s^2", self.profile_vars[2]),
            ("Profile Jerk mm/s^3", self.profile_vars[3]),
        ]
        for index, (label, var) in enumerate(profile_fields):
            label_widget = ttk.Label(profile_frame, text=label)
            self.profile_label_widgets.append(label_widget)
            label_widget.grid(
                row=0,
                column=index * 2,
                padx=5,
                pady=5,
                sticky="e",
            )
            entry = ttk.Entry(profile_frame, textvariable=var, justify="right", width=14)
            entry.bind(
                "<KeyRelease>",
                lambda _event, watched_var=var: self.mark_dirty(watched_var),
            )
            self.bind_entry_focus(entry, var)
            entry.grid(row=0, column=index * 2 + 1, padx=5, pady=5, sticky="ew")
            self.profile_entry_widgets.append(entry)
            profile_frame.columnconfigure(index * 2 + 1, weight=1)

        settings_buttons = ttk.Frame(settings_tab)
        settings_buttons.pack(fill="x", pady=(4, 0))
        ttk.Button(
            settings_buttons,
            text="Apply PP Profile",
            command=self.apply_profile_settings,
        ).pack(side="left", padx=4)

        limit_frame = ttk.LabelFrame(limits_tab, text="Selected Axis Motion Limits")
        limit_frame.pack(fill="x", pady=(0, 10))
        limit_fields = [
            ("Max Profile Velocity (+) mm/s", self.limit_vars[0]),
            ("Max Profile Velocity (-) mm/s", self.limit_vars[1]),
            ("Max Accel mm/s^2", self.limit_vars[2]),
            ("Max Decel mm/s^2", self.limit_vars[3]),
        ]
        for index, (label, var) in enumerate(limit_fields):
            label_widget = ttk.Label(limit_frame, text=label)
            self.limit_label_widgets.append(label_widget)
            label_widget.grid(
                row=0,
                column=index * 2,
                padx=5,
                pady=5,
                sticky="e",
            )
            entry = ttk.Entry(limit_frame, textvariable=var, justify="right", width=14)
            entry.bind(
                "<KeyRelease>",
                lambda _event, watched_var=var: self.mark_dirty(watched_var),
            )
            self.bind_entry_focus(entry, var)
            entry.grid(row=0, column=index * 2 + 1, padx=5, pady=5, sticky="ew")
            limit_frame.columnconfigure(index * 2 + 1, weight=1)

        sw_limit_frame = ttk.LabelFrame(limits_tab, text="Selected Axis Software Position Limits")
        sw_limit_frame.pack(fill="x", pady=(0, 10))
        sw_limit_fields = [
            ("Negative SW Limit mm", self.software_limit_vars[0]),
            ("Positive SW Limit mm", self.software_limit_vars[1]),
        ]
        for index, (label, var) in enumerate(sw_limit_fields):
            label_widget = ttk.Label(sw_limit_frame, text=label)
            self.software_limit_label_widgets.append(label_widget)
            label_widget.grid(
                row=0,
                column=index * 2,
                padx=5,
                pady=5,
                sticky="e",
            )
            entry = ttk.Entry(sw_limit_frame, textvariable=var, justify="right", width=14)
            entry.bind(
                "<KeyRelease>",
                lambda _event, watched_var=var: self.mark_dirty(watched_var),
            )
            self.bind_entry_focus(entry, var)
            entry.grid(row=0, column=index * 2 + 1, padx=5, pady=5, sticky="ew")
            sw_limit_frame.columnconfigure(index * 2 + 1, weight=1)

        limit_buttons = ttk.Frame(limits_tab)
        limit_buttons.pack(fill="x", pady=(4, 0))
        ttk.Button(
            limit_buttons,
            text="Apply Motion Limits",
            command=self.apply_motion_limits,
        ).pack(
            side="left",
            padx=4,
        )
        ttk.Button(
            limit_buttons,
            text="Apply SW Limits",
            command=self.apply_software_limits,
        ).pack(
            side="left",
            padx=4,
        )

        diagnosis_frame = ttk.LabelFrame(diagnosis_tab, text="Selected Axis SDO")
        diagnosis_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(diagnosis_frame, text="Catalog").grid(
            row=0,
            column=0,
            padx=5,
            pady=5,
            sticky="e",
        )
        self.diagnosis_catalog_combo = ttk.Combobox(
            diagnosis_frame,
            textvariable=self.diagnosis_catalog_var,
            width=48,
            state="readonly",
        )
        self.diagnosis_catalog_combo.grid(
            row=0,
            column=1,
            columnspan=7,
            padx=5,
            pady=5,
            sticky="ew",
        )
        self.diagnosis_catalog_combo.bind(
            "<<ComboboxSelected>>",
            self.on_diagnosis_catalog_selected,
        )
        ttk.Button(
            diagnosis_frame,
            text="Load Catalog",
            command=self.load_diagnosis_catalog,
        ).grid(row=0, column=8, columnspan=2, padx=5, pady=5, sticky="ew")

        self.diagnosis_catalog_detail_text = scrolledtext.ScrolledText(
            diagnosis_frame,
            height=3,
            wrap="word",
            state="disabled",
        )
        self.diagnosis_catalog_detail_text.grid(
            row=1,
            column=0,
            columnspan=10,
            padx=5,
            pady=(0, 5),
            sticky="ew",
        )

        diagnosis_fields = [
            ("Index", self.diagnosis_index_var, "entry"),
            ("Subindex", self.diagnosis_subindex_var, "entry"),
            ("Type", self.diagnosis_type_var, "combo"),
            ("Length", self.diagnosis_length_var, "entry"),
            ("Value", self.diagnosis_value_var, "entry"),
        ]
        for index, (label, var, kind) in enumerate(diagnosis_fields):
            ttk.Label(diagnosis_frame, text=label).grid(
                row=2,
                column=index * 2,
                padx=5,
                pady=5,
                sticky="e",
            )
            if kind == "combo":
                widget = ttk.Combobox(
                    diagnosis_frame,
                    textvariable=var,
                    values=[
                        "uint8",
                        "int8",
                        "uint16",
                        "int16",
                        "int32",
                        "uint32",
                        "udint",
                        "float32",
                        "string",
                    ],
                    width=12,
                    state="readonly",
                )
            else:
                widget = ttk.Entry(
                    diagnosis_frame,
                    textvariable=var,
                    justify="right",
                    width=14,
                )
                self.bind_entry_focus(widget, var)
            widget.grid(
                row=2,
                column=index * 2 + 1,
                padx=5,
                pady=5,
                sticky="ew",
            )
            diagnosis_frame.columnconfigure(index * 2 + 1, weight=1)

        diagnosis_buttons = ttk.Frame(diagnosis_tab)
        diagnosis_buttons.pack(fill="x", pady=(4, 8))
        ttk.Button(
            diagnosis_buttons,
            text="Read",
            command=self.diagnosis_read,
        ).pack(side="left", padx=4)
        ttk.Button(
            diagnosis_buttons,
            text="Write",
            command=self.diagnosis_write,
        ).pack(side="left", padx=4)
        ttk.Button(
            diagnosis_buttons,
            text="Parameter Save",
            command=self.diagnosis_parameter_save,
        ).pack(side="left", padx=4)
        ttk.Button(
            diagnosis_buttons,
            text="Axis Restart",
            command=self.axis_restart,
        ).pack(side="left", padx=4)
        ttk.Label(
            diagnosis_buttons,
            textvariable=self.diagnosis_unit_var,
        ).pack(side="right", padx=4)

        diagnosis_result = ttk.LabelFrame(diagnosis_tab, text="Result")
        diagnosis_result.pack(fill="both", expand=True)
        ttk.Label(
            diagnosis_result,
            textvariable=self.diagnosis_result_var,
            anchor="nw",
            justify="left",
            wraplength=1080,
        ).pack(fill="both", expand=True, padx=6, pady=6)

        traces = ttk.Frame(self.single_axis_area)
        traces.pack(fill="both", expand=True)
        self.position_trace = TraceCanvas(
            traces,
            ["Actual Position mm", "Target Position mm"],
            "Position",
        )
        self.velocity_trace = TraceCanvas(
            traces,
            ["Actual Velocity mm/s"],
            "Velocity",
            2,
        )
        self._build_multi_axis_ui(self.multi_axis_area)
