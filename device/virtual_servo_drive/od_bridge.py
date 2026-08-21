class VirtualOdBridge:
    """Connect EtherCAT OD access and process images to one OD Model."""

    def __init__(self, axis_or_od_model, rxpdo, txpdo):
        self.axis = axis_or_od_model if hasattr(axis_or_od_model, "servo") else None
        self.od_model = self._resolve_od_model(axis_or_od_model)
        self.rxpdo = rxpdo
        self.txpdo = txpdo

    @staticmethod
    def _resolve_od_model(owner):
        if hasattr(owner, "read") and hasattr(owner, "write"):
            return owner
        if hasattr(owner, "od"):
            return owner.od
        return owner.servo.od

    def read(self, index, subindex=0):
        return self.od_model.read(index, subindex)

    def write(self, index, value, subindex=0):
        self.od_model.write(index, value, subindex)

    def rxpdo_to_od(self):
        for obj in self.rxpdo.mapping:
            if obj.index != 0 and obj.field is not None:
                self.write(obj.index, getattr(self.rxpdo, obj.field), obj.subindex)

    def od_to_txpdo(self):
        for obj in self.txpdo.mapping:
            if obj.index != 0 and obj.field is not None:
                setattr(self.txpdo, obj.field, self.read(obj.index, obj.subindex))

    def rxpdo_to_axis(self):
        # Compatibility adapter until TD-004 removes Axis. The setters retain
        # existing mode-transition side effects while writing the same OD Model.
        if self.axis is None:
            self.rxpdo_to_od()
            return
        self.axis.set_controlword(self.rxpdo.controlword)
        self.axis.set_mode(self.rxpdo.mode_of_operation)
        if self.rxpdo.has_field("target_position"):
            self.axis.set_target_position(self.rxpdo.target_position)
        if self.rxpdo.has_field("profile_velocity"):
            self.axis.set_profile_velocity(self.rxpdo.profile_velocity)
        if self.rxpdo.has_field("target_velocity"):
            self.axis.set_target_velocity(self.rxpdo.target_velocity)
        handled = {
            "controlword", "mode_of_operation", "target_position",
            "profile_velocity", "target_velocity",
        }
        for obj in self.rxpdo.mapping:
            if obj.index != 0 and obj.field is not None and obj.field not in handled:
                self.write(obj.index, getattr(self.rxpdo, obj.field), obj.subindex)

    def axis_to_txpdo(self):
        self.od_to_txpdo()
        # setpoint_position is a synthetic legacy field, not an OD value.
        if (
            self.txpdo.has_field("setpoint_position")
            and self.rxpdo.has_field("target_position")
        ):
            self.txpdo.setpoint_position = self.rxpdo.target_position
