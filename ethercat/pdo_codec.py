import struct


class CiA402PdoCodec:
    rxpdo_struct = struct.Struct("<HbiIihihb")
    txpdo_struct = struct.Struct("<Hbiihb")
    txpdo_setpoint_struct = struct.Struct("<Hbiihib")
    txpdo_lint_setpoint_struct = struct.Struct("<Hbiihqb")

    @classmethod
    def encode_rxpdo(cls, rxpdo):
        return cls.rxpdo_struct.pack(
            int(rxpdo.controlword),
            int(rxpdo.mode_of_operation),
            int(rxpdo.target_position),
            int(rxpdo.profile_velocity),
            int(rxpdo.target_velocity),
            int(rxpdo.target_torque),
            int(rxpdo.velocity_offset),
            int(rxpdo.torque_offset),
            0,
        )

    @classmethod
    def decode_rxpdo(cls, payload, rxpdo):
        if len(payload) < cls.rxpdo_struct.size:
            raise ValueError(
                "RxPDO payload is too small. "
                f"Expected at least {cls.rxpdo_struct.size} bytes, "
                f"got {len(payload)} bytes."
            )

        (
            rxpdo.controlword,
            rxpdo.mode_of_operation,
            rxpdo.target_position,
            rxpdo.profile_velocity,
            rxpdo.target_velocity,
            rxpdo.target_torque,
            rxpdo.velocity_offset,
            rxpdo.torque_offset,
            _padding,
        ) = cls.rxpdo_struct.unpack(bytes(payload[:cls.rxpdo_struct.size]))

    @classmethod
    def decode_txpdo(cls, payload, txpdo):
        if len(payload) < cls.txpdo_struct.size:
            raise ValueError(
                "TxPDO payload is too small. "
                f"Expected at least {cls.txpdo_struct.size} bytes, "
                f"got {len(payload)} bytes."
            )

        (
            txpdo.statusword,
            txpdo.mode_of_operation_display,
            txpdo.actual_position,
            txpdo.actual_velocity,
            txpdo.actual_torque,
            _padding,
        ) = cls.txpdo_struct.unpack(bytes(payload[:cls.txpdo_struct.size]))
        txpdo.setpoint_position = 0

    @classmethod
    def decode_txpdo_with_setpoint(cls, payload, txpdo, feedback_object="6062"):
        feedback_object = str(feedback_object).strip().lower()
        if feedback_object in ("217a01", "0x217a:01", "0x217a01"):
            return cls.decode_txpdo_with_lint_setpoint(payload, txpdo)

        if len(payload) < cls.txpdo_setpoint_struct.size:
            raise ValueError(
                "TxPDO payload is too small. "
                f"Expected at least {cls.txpdo_setpoint_struct.size} bytes, "
                f"got {len(payload)} bytes."
            )

        (
            txpdo.statusword,
            txpdo.mode_of_operation_display,
            txpdo.actual_position,
            txpdo.actual_velocity,
            txpdo.actual_torque,
            txpdo.setpoint_position,
            _padding,
        ) = cls.txpdo_setpoint_struct.unpack(
            bytes(payload[:cls.txpdo_setpoint_struct.size])
        )

    @classmethod
    def decode_txpdo_with_lint_setpoint(cls, payload, txpdo):
        if len(payload) < cls.txpdo_lint_setpoint_struct.size:
            raise ValueError(
                "TxPDO payload is too small. "
                f"Expected at least {cls.txpdo_lint_setpoint_struct.size} bytes, "
                f"got {len(payload)} bytes."
            )

        (
            txpdo.statusword,
            txpdo.mode_of_operation_display,
            txpdo.actual_position,
            txpdo.actual_velocity,
            txpdo.actual_torque,
            txpdo.setpoint_position,
            _padding,
        ) = cls.txpdo_lint_setpoint_struct.unpack(
            bytes(payload[:cls.txpdo_lint_setpoint_struct.size])
        )

    @classmethod
    def rxpdo_size(cls):
        return cls.rxpdo_struct.size

    @classmethod
    def txpdo_size(cls):
        return cls.txpdo_struct.size

    @classmethod
    def txpdo_setpoint_size(cls):
        return cls.txpdo_setpoint_struct.size
