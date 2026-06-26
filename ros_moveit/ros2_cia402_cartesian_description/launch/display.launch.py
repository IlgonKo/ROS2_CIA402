from launch import LaunchDescription
from launch.substitutions import Command
from launch.substitutions import FindExecutable
from launch.substitutions import PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    robot_description_content = Command(
        [
            FindExecutable(name="xacro"),
            " ",
            PathJoinSubstitution(
                [
                    FindPackageShare("ros2_cia402_cartesian_description"),
                    "urdf",
                    "cartesian_3axis.urdf.xacro",
                ]
            ),
        ]
    )

    robot_description = {
        "robot_description": robot_description_content,
    }

    return LaunchDescription(
        [
            Node(
                package="robot_state_publisher",
                executable="robot_state_publisher",
                parameters=[robot_description],
                output="screen",
            ),
            Node(
                package="joint_state_publisher_gui",
                executable="joint_state_publisher_gui",
                output="screen",
            ),
            Node(
                package="rviz2",
                executable="rviz2",
                output="screen",
            ),
        ]
    )
