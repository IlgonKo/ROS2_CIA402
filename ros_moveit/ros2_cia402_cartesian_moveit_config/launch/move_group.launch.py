from launch import LaunchDescription
from launch_ros.actions import Node
from moveit_configs_utils import MoveItConfigsBuilder


def generate_launch_description():
    moveit_config = (
        MoveItConfigsBuilder(
            "ros2_cia402_cartesian_3axis",
            package_name="ros2_cia402_cartesian_moveit_config",
        )
        .robot_description(
            file_path="config/cartesian_3axis.urdf.xacro"
        )
        .robot_description_semantic(
            file_path="config/ros2_cia402_cartesian_3axis.srdf"
        )
        .trajectory_execution(file_path="config/moveit_controllers.yaml")
        .planning_pipelines(pipelines=["ompl"])
        .to_moveit_configs()
    )

    return LaunchDescription(
        [
            Node(
                package="moveit_ros_move_group",
                executable="move_group",
                output="screen",
                parameters=[moveit_config.to_dict()],
            )
        ]
    )
