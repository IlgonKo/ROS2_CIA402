FROM osrf/ros:jazzy-desktop

SHELL ["/bin/bash", "-c"]

ENV DEBIAN_FRONTEND=noninteractive
ENV ROS_DISTRO=jazzy
ENV PYTHONPATH=/workspace
ENV PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y \
    libgl1-mesa-dri \
    mesa-utils \
    python3-colcon-common-extensions \
    python3-rosdep \
    python3-vcstool \
    ros-jazzy-moveit \
    ros-jazzy-rmw-cyclonedds-cpp \
    ros-jazzy-joint-state-publisher-gui \
    ros-jazzy-robot-state-publisher \
    ros-jazzy-xacro \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

RUN echo "source /opt/ros/jazzy/setup.bash" >> /root/.bashrc
RUN echo "export PYTHONPATH=/workspace:\$PYTHONPATH" >> /root/.bashrc

CMD ["/bin/bash"]
