# ROS2 CiA402 Cartesian MoveIt Config

This package is a hand-written MoveIt configuration for the simple 3-axis
Cartesian test robot. It avoids the MoveIt Setup Assistant RViz preview, which
can crash in Windows Docker/X11 environments.

Planning group:

```text
cartesian_arm
```

Joints:

```text
X, Y, Z
```

Controller action expected by MoveIt:

```text
/cia402_joint_trajectory_controller/follow_joint_trajectory
```

The Bridge provides this action server and forwards accepted trajectory targets
to the Axis Server.
