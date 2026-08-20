from dataclasses import dataclass


@dataclass(frozen=True)
class CommandSpec:
    name: str
    kind: str
    authority_required: bool = False
    advanced_only: bool = False
    initialization_error_allowed: bool = False

    @property
    def is_command(self):
        return self.kind == "command"

    @property
    def is_status(self):
        return self.kind == "status"

    @property
    def is_authority(self):
        return self.kind == "authority"


def command(
    name,
    authority_required=True,
    advanced_only=False,
    initialization_error_allowed=False,
):
    return CommandSpec(
        name,
        "command",
        authority_required=authority_required,
        advanced_only=advanced_only,
        initialization_error_allowed=initialization_error_allowed,
    )


def status(name, advanced_only=False):
    return CommandSpec(name, "status", advanced_only=advanced_only)


def authority(name):
    return CommandSpec(name, "authority")


COMMAND_SPECS = {
    spec.name: spec
    for spec in (
        authority("system/authority/request"),
        authority("system/authority/release"),
        authority("system/authority/status"),
        status("system/server/status"),
        status("system/bus/status"),
        status("system/axis/status"),
        status("system/axes/status"),
        status("system/io/status"),
        status("system/io/input_read"),
        status("system/axis/param_read"),
        status("system/axis/param_catalog"),
        status("system/io/param_read"),
        status("system/io/ethercat/param_catalog"),
        status("system/io/ap/param_catalog"),
        status("system/io/iol/param_catalog"),
        status("system/io/ap/param_read"),
        status("system/io/iol/param_read"),
        command("system/server/reset", initialization_error_allowed=True),
        command("system/server/restart", initialization_error_allowed=True),
        command("system/bus/reconnect", initialization_error_allowed=True),
        command("system/bus/rescan", initialization_error_allowed=True),
        command("system/axis/enable"),
        command("system/axis/disable"),
        command("system/axis/reset"),
        command("system/axis/restart"),
        command("system/axis/home"),
        command("system/axis/stop"),
        command("system/axis/move_abs"),
        command("system/axis/move_rel"),
        command("system/axis/move_vel"),
        command("system/axis/jog_start"),
        command("system/axis/jog_stop"),
        command("system/axis/profile"),
        command("system/axis/motion_limits"),
        command("system/axis/software_position_limits"),
        command("system/axis/mode"),
        command("system/axis/manualCW", advanced_only=True),
        command("system/axis/param_write"),
        command("system/axis/param_save"),
        command("system/axes/enable"),
        command("system/axes/disable"),
        command("system/axes/reset"),
        command("system/axes/stop"),
        command("system/axes/move_abs"),
        command("system/axes/move_rel"),
        command("system/axes/move_vel"),
        command("system/axes/trajectory", advanced_only=True),
        command("system/axes/trajectory_stop", advanced_only=True),
        command("system/io/output_write"),
        command("system/io/reset"),
        command("system/io/restart"),
        command("system/io/param_write"),
        command("system/io/param_save"),
        command("system/io/ap/param_write"),
        command("system/io/iol/param_write"),
    )
}


def command_spec(name):
    return COMMAND_SPECS.get(str(name or "").strip())


def command_names():
    return set(COMMAND_SPECS)


def command_message_types():
    return {
        name
        for name, spec in COMMAND_SPECS.items()
        if spec.is_command and spec.authority_required
    }


def authority_message_types():
    return {
        name
        for name, spec in COMMAND_SPECS.items()
        if spec.is_authority
    }


def status_message_types():
    return {
        name
        for name, spec in COMMAND_SPECS.items()
        if spec.is_status
    }


def advanced_message_types():
    return {
        name
        for name, spec in COMMAND_SPECS.items()
        if spec.advanced_only and spec.is_command
    }


def advanced_status_message_types():
    return {
        name
        for name, spec in COMMAND_SPECS.items()
        if spec.advanced_only and spec.is_status
    }


def initialization_error_allowed_command_types():
    return {
        name
        for name, spec in COMMAND_SPECS.items()
        if spec.initialization_error_allowed
    }
