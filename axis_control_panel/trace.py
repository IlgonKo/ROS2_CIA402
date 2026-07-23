"""Trace canvas widget for Axis Control Panel."""

import tkinter as tk


HISTORY_SIZE = 500


class TraceCanvas:
    def __init__(self, parent, series_names, title, color_offset=0):
        self.series_names = series_names
        self.title = title
        self.history = [
            []
            for _ in series_names
        ]
        self.colors = [
            "#ff5a5f",
            "#2ecc71",
            "#3498db",
            "#f1c40f",
            "#9b59b6",
            "#1abc9c",
        ]
        self.color_offset = color_offset
        self.canvas = tk.Canvas(parent, height=190, bg="#202020", highlightthickness=1)
        self.canvas.pack(fill="both", expand=True, padx=5, pady=5)

    def set_series_names(self, series_names):
        if self.series_names == series_names:
            return

        self.series_names = series_names
        self.history = [
            []
            for _ in series_names
        ]

    def add_sample(self, values):
        for index, value in enumerate(values[:len(self.history)]):
            series = self.history[index]
            series.append(float(value))
            if len(series) > HISTORY_SIZE:
                del series[0]

    def draw(self):
        self.canvas.delete("all")
        width = max(self.canvas.winfo_width(), 50)
        height = max(self.canvas.winfo_height(), 50)
        margin = 28

        all_values = [
            value
            for series in self.history
            for value in series
        ]
        if not all_values:
            self._draw_empty(width, height)
            return

        min_value = min(all_values)
        max_value = max(all_values)
        if abs(max_value - min_value) < 1e-9:
            min_value -= 1.0
            max_value += 1.0

        self.canvas.create_text(
            8,
            8,
            text=self.title,
            fill="#f0f0f0",
            anchor="nw",
            font=("TkDefaultFont", 10, "bold"),
        )
        self.canvas.create_text(
            width - 8,
            8,
            text=f"{min_value:.1f} .. {max_value:.1f}",
            fill="#cfcfcf",
            anchor="ne",
        )

        for step in range(5):
            y = margin + step * (height - margin * 2) / 4
            self.canvas.create_line(
                margin,
                y,
                width - margin,
                y,
                fill="#343434",
            )

        for index, series in enumerate(self.history):
            if len(series) < 2:
                continue

            color = self.colors[(index + self.color_offset) % len(self.colors)]
            points = []
            for sample_index, value in enumerate(series):
                x = margin + sample_index * (width - margin * 2) / (HISTORY_SIZE - 1)
                normalized = (value - min_value) / (max_value - min_value)
                y = height - margin - normalized * (height - margin * 2)
                points.extend([x, y])

            self.canvas.create_line(*points, fill=color, width=2)

        self._draw_legend(width, height, margin)

    def _draw_empty(self, width, height):
        self.canvas.create_text(
            width / 2,
            height / 2,
            text="Waiting for feedback",
            fill="#bdbdbd",
        )

    def _draw_legend(self, width, height, margin):
        x = margin + 8
        y = height - 14
        line_height = 15

        for index, text in enumerate(self.series_names):
            color = self.colors[(index + self.color_offset) % len(self.colors)]
            item = self.canvas.create_text(
                x,
                y,
                text=text,
                fill=color,
                anchor="w",
                font=("TkDefaultFont", 9),
            )
            bbox = self.canvas.bbox(item)
            if bbox is not None and bbox[2] > width - margin and x > margin + 8:
                self.canvas.move(item, margin + 8 - x, -line_height)
                x = margin + 8
                y -= line_height
                bbox = self.canvas.bbox(item)

            if bbox is not None and bbox[2] > width - margin:
                compact_text = self._compact_legend_text(text)
                self.canvas.itemconfigure(item, text=compact_text)
                bbox = self.canvas.bbox(item)

            if bbox is not None:
                x = bbox[2] + 18

    def _compact_legend_text(self, text):
        return (
            text.replace("Actual ", "Act ")
            .replace("Target ", "Tgt ")
            .replace("Command ", "Cmd ")
            .replace("Position", "Pos")
            .replace("Velocity", "Vel")
            .replace(" mm/s", "")
            .replace(" mm", "")
        )


class TraceMixin:
    def reset_multi_traces(self):
        if self.multi_position_trace is not None:
            self.multi_position_trace.history = [
                []
                for _ in self.multi_position_trace.series_names
            ]
        if self.multi_velocity_trace is not None:
            self.multi_velocity_trace.history = [
                []
                for _ in self.multi_velocity_trace.series_names
            ]

    def selected_multi_trace_axes(self):
        axes = [
            axis_index
            for axis_index, var in enumerate(self.multi_trace_axis_vars)
            if var.get()
        ]
        return axes or [0]

    def multi_trace_series_names(self, axes, value_name):
        names = []
        for axis_index in axes:
            pos_unit, vel_unit, _accel_unit, _jerk_unit = self.axis_unit_labels(axis_index)
            unit = vel_unit if "Velocity" in value_name else pos_unit
            names.append(f"{self.axis_names[axis_index]} {value_name} {unit}")
        return names
