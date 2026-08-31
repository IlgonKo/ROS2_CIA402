from windows_runtime import prepare_io_control_panel_runtime


prepare_io_control_panel_runtime()

from control_panel.io_control_panel.control_panel import main


if __name__ == "__main__":
    main()
