# ROS2_CIA402 MoveIt Test Models

This folder contains ROS packages used for MoveIt integration tests.

## Cartesian 3-Axis Description

Package:

```text
ros2_cia402_cartesian_description
```

Robot model:

```text
base_link
  -> X prismatic joint
  -> Y prismatic joint
  -> Z prismatic joint
  -> tool0
```

The joint names intentionally match the default Bridge axis names:

```text
X, Y, Z
```

MoveIt uses SI units, so the prismatic joint limits in the xacro are meters.
The current Bridge forwards joint positions as-is. Before real execution with
drives, confirm whether an additional unit conversion layer is needed.
