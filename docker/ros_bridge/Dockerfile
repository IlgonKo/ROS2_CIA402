FROM ros:jazzy-ros-base

SHELL ["/bin/bash", "-c"]

ENV DEBIAN_FRONTEND=noninteractive
ENV ROS_DISTRO=jazzy
ENV PYTHONPATH=/workspace
ENV PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y \
    ros-jazzy-control-msgs \
    ros-jazzy-rclpy \
    ros-jazzy-rcl-interfaces \
    ros-jazzy-sensor-msgs \
    ros-jazzy-std-msgs \
    ros-jazzy-trajectory-msgs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

RUN echo "source /opt/ros/jazzy/setup.bash" >> /root/.bashrc
RUN echo "export PYTHONPATH=/workspace:\$PYTHONPATH" >> /root/.bashrc

CMD ["/bin/bash"]
