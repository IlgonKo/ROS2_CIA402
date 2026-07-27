"""Motion Server connection helpers for Axis Control Panel."""
from tkinter import messagebox


class ConnectionMixin:
    def apply_server_endpoint(self):
        host = self.server_host_var.get().strip()
        if not host:
            messagebox.showerror("Invalid Input", "Server host is required.")
            return

        try:
            port = int(self.server_port_var.get())
        except ValueError:
            messagebox.showerror("Invalid Input", "Server port must be numeric.")
            return

        if port < 1 or port > 65535:
            messagebox.showerror("Invalid Input", "Server port must be 1..65535.")
            return

        self.stop_tab_motion()
        self.client.set_endpoint(host, port)
        self.panel_sdo_read_connected = False
        self.connection_var.set(f"Reconnecting {host}:{port}")

    def toggle_server_connection(self):
        connected, _error, _feedback, _notice, _diagnosis_result = self.client.get_snapshot()
        if connected:
            self.stop_tab_motion()
            self.client.disconnect()
            self.connection_var.set("Disconnected by user")
            self.update_connection_button(False)
            return

        self.client.enable_connection()
        self.apply_server_endpoint()

    def update_connection_button(self, connected):
        self.connection_button_var.set("Disconnect" if connected else "Connect")
        if self.connection_button is not None:
            self.connection_button.configure(
                style="Connected.TButton" if connected else "TButton"
            )

    def try_send(self, send_func):
        try:
            send_func()
            return True
        except Exception as exc:
            messagebox.showerror("Send Failed", str(exc))
            return False
