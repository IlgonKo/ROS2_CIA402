"""Multi-axis UI builder for Axis Control Panel."""

from tkinter import ttk

from control_panel.axis_control_panel.trace import TraceCanvas


class MultiAxisViewBuilderMixin:
    def _build_multi_axis_ui(self, parent):
        command_frame = ttk.LabelFrame(parent, text="Multi Axis Position Command")
        command_frame.pack(fill="x", pady=(0, 10))

        headings = [
            "Use",
            "Axis",
            "Mode",
            "Command",
            "Value",
            "Profile Velocity",
            "Value",
            "Actual Position",
        ]
        for column, text in enumerate(headings):
            ttk.Label(command_frame, text=text).grid(
                row=0,
                column=column,
                padx=5,
                pady=5,
                sticky="ew",
            )
            command_frame.columnconfigure(column, weight=1 if column in (4, 6, 7) else 0)

        for axis_index, axis_name in enumerate(self.axis_names):
            row = axis_index + 1
            ttk.Checkbutton(
                command_frame,
                variable=self.multi_axis_vars[axis_index],
            ).grid(row=row, column=0, padx=5, pady=4)
            ttk.Label(command_frame, text=axis_name).grid(
                row=row,
                column=1,
                padx=5,
                pady=4,
                sticky="w",
            )
            mode_combo = ttk.Combobox(
                command_frame,
                textvariable=self.multi_motion_mode_vars[axis_index],
                values=self.motion_mode_options(axis_index),
                state="readonly",
                width=5,
            )
            mode_combo.bind(
                "<<ComboboxSelected>>",
                lambda _event, axis=axis_index: self.on_multi_motion_mode_changed(axis),
            )
            mode_combo.grid(row=row, column=2, padx=5, pady=4, sticky="ew")
            self.multi_mode_widgets.append(mode_combo)

            command_label = ttk.Label(command_frame, text="Target Position")
            command_label.grid(row=row, column=3, padx=5, pady=4, sticky="e")
            self.multi_command_label_widgets.append(command_label)
            target_entry = ttk.Entry(
                command_frame,
                textvariable=self.multi_target_position_vars[axis_index],
                justify="right",
                width=16,
            )
            target_entry.bind(
                "<KeyRelease>",
                lambda _event, watched_var=self.multi_target_position_vars[axis_index]: (
                    self.mark_dirty(watched_var)
                ),
            )
            self.bind_entry_focus(
                target_entry,
                self.multi_target_position_vars[axis_index],
            )
            target_entry.grid(row=row, column=4, padx=5, pady=4, sticky="ew")

            profile_label = ttk.Label(command_frame, text="Profile Velocity")
            profile_label.grid(row=row, column=5, padx=5, pady=4, sticky="e")
            self.multi_profile_label_widgets.append(profile_label)
            velocity_entry = ttk.Entry(
                command_frame,
                textvariable=self.multi_profile_velocity_vars[axis_index],
                justify="right",
                width=16,
            )
            velocity_entry.bind(
                "<KeyRelease>",
                lambda _event, watched_var=self.multi_profile_velocity_vars[axis_index]: (
                    self.mark_dirty(watched_var)
                ),
            )
            self.bind_entry_focus(
                velocity_entry,
                self.multi_profile_velocity_vars[axis_index],
            )
            velocity_entry.grid(row=row, column=6, padx=5, pady=4, sticky="ew")
            self.multi_profile_entry_widgets.append(velocity_entry)

            ttk.Label(
                command_frame,
                textvariable=self.multi_actual_position_vars[axis_index],
                anchor="e",
                width=16,
            ).grid(row=row, column=7, padx=5, pady=4, sticky="ew")

        buttons = ttk.Frame(parent)
        buttons.pack(fill="x", pady=(0, 10))
        ttk.Button(buttons, text="Run", command=self.multi_axis_run).pack(
            side="left",
            padx=4,
        )
        ttk.Button(buttons, text="Stop", command=self.multi_axis_stop).pack(
            side="left",
            padx=4,
        )
        ttk.Button(buttons, text="Homing", command=self.multi_axis_homing).pack(
            side="left",
            padx=4,
        )
        ttk.Button(buttons, text="Fault Reset", command=self.multi_axis_fault_reset).pack(
            side="left",
            padx=4,
        )

        repeat_frame = ttk.LabelFrame(parent, text="Multi Axis Repeat Motion")
        repeat_frame.pack(fill="x", pady=(0, 10))
        repeat_headings = [
            "Use",
            "Axis",
            "Mode",
            "A",
            "Value",
            "B",
            "Value",
            "Profile Velocity",
            "Value",
        ]
        for column, text in enumerate(repeat_headings):
            ttk.Label(repeat_frame, text=text).grid(
                row=0,
                column=column,
                padx=5,
                pady=5,
                sticky="ew",
            )
            repeat_frame.columnconfigure(column, weight=1 if column in (4, 6, 8) else 0)

        for axis_index, axis_name in enumerate(self.axis_names):
            row = axis_index + 1
            ttk.Checkbutton(
                repeat_frame,
                variable=self.multi_axis_vars[axis_index],
            ).grid(row=row, column=0, padx=5, pady=4)
            ttk.Label(repeat_frame, text=axis_name).grid(
                row=row,
                column=1,
                padx=5,
                pady=4,
                sticky="w",
            )
            repeat_mode_combo = ttk.Combobox(
                repeat_frame,
                textvariable=self.multi_motion_mode_vars[axis_index],
                values=self.motion_mode_options(axis_index),
                state="readonly",
                width=5,
            )
            repeat_mode_combo.bind(
                "<<ComboboxSelected>>",
                lambda _event, axis=axis_index: self.on_multi_motion_mode_changed(axis),
            )
            repeat_mode_combo.grid(row=row, column=2, padx=5, pady=4, sticky="ew")
            self.multi_mode_widgets.append(repeat_mode_combo)

            a_label = ttk.Label(repeat_frame, text="Point A")
            a_label.grid(row=row, column=3, padx=5, pady=4, sticky="e")
            self.multi_repeat_a_label_widgets.append(a_label)
            b_label = ttk.Label(repeat_frame, text="Point B")
            b_label.grid(row=row, column=5, padx=5, pady=4, sticky="e")
            self.multi_repeat_b_label_widgets.append(b_label)
            profile_label = ttk.Label(repeat_frame, text="Profile Velocity")
            profile_label.grid(row=row, column=7, padx=5, pady=4, sticky="e")
            self.multi_repeat_profile_label_widgets.append(profile_label)

            for column, var in [
                (4, self.multi_repeat_point_a_vars[axis_index]),
                (6, self.multi_repeat_point_b_vars[axis_index]),
                (8, self.multi_repeat_profile_velocity_vars[axis_index]),
            ]:
                entry = ttk.Entry(
                    repeat_frame,
                    textvariable=var,
                    justify="right",
                    width=16,
                )
                entry.bind(
                    "<KeyRelease>",
                    lambda _event, watched_var=var: self.mark_dirty(watched_var),
                )
                self.bind_entry_focus(entry, var)
                entry.grid(row=row, column=column, padx=5, pady=4, sticky="ew")
                if column == 8:
                    self.multi_repeat_profile_entry_widgets.append(entry)

        repeat_controls = ttk.Frame(parent)
        repeat_controls.pack(fill="x", pady=(0, 10))
        ttk.Label(repeat_controls, text="Period (s)").pack(
            side="left",
            padx=(4, 5),
        )
        entry = ttk.Entry(
            repeat_controls,
            textvariable=self.multi_repeat_period_var,
            justify="right",
            width=10,
        )
        self.bind_entry_focus(entry, self.multi_repeat_period_var)
        entry.pack(side="left", padx=4)
        ttk.Button(
            repeat_controls,
            text="Start Repeat",
            command=self.start_multi_repeat,
        ).pack(side="left", padx=(12, 4))
        ttk.Button(
            repeat_controls,
            text="Stop Repeat",
            command=self.stop_multi_repeat_motion,
        ).pack(side="left", padx=4)

        trace_controls = ttk.Frame(parent)
        trace_controls.pack(fill="x", pady=(0, 4))
        ttk.Label(trace_controls, text="Trace Axes").pack(
            side="left",
            padx=(4, 5),
        )
        for axis_index, axis_name in enumerate(self.axis_names):
            ttk.Checkbutton(
                trace_controls,
                text=axis_name,
                variable=self.multi_trace_axis_vars[axis_index],
            ).pack(side="left", padx=4)

        traces = ttk.Frame(parent)
        traces.pack(fill="both", expand=True)
        self.multi_position_trace = TraceCanvas(
            traces,
            ["Actual Position mm"],
            "Position",
        )
        self.multi_velocity_trace = TraceCanvas(
            traces,
            ["Actual Velocity mm/s"],
            "Velocity",
            2,
        )
