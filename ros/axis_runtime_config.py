"""Temporary ROS axis defaults until ROS consumes the common config model.

ROS must not parse the Motion Server project configuration or bus layout on its
own. The defaults below only keep the existing ROS bridge import contract
working while common-model integration is deferred.
"""


DEFAULT_AXIS_NAMES = ("X", "Y", "Z")


def get_axis_names():
    return list(DEFAULT_AXIS_NAMES)


def get_axis_count():
    return len(DEFAULT_AXIS_NAMES)
