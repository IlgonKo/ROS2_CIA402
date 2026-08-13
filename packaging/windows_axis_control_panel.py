from windows_runtime import prepare_axis_control_panel_runtime


prepare_axis_control_panel_runtime()

from control_panel.axis_control_panel.control_panel import main


if __name__ == "__main__":
    main()
