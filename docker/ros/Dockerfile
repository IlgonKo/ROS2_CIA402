FROM osrf/ros:jazzy-desktop

SHELL ["/bin/bash", "-c"]

ENV DEBIAN_FRONTEND=noninteractive
ENV ROS_DISTRO=jazzy
ENV PYTHONPATH=/workspace

RUN apt-get update && apt-get install -y \
    python3-pip \
    python3-colcon-common-extensions \
    python3-tk \
    x11-apps \
    ros-jazzy-rclpy \
    ros-jazzy-std-msgs \
    ros-jazzy-demo-nodes-py \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

RUN echo "source /opt/ros/jazzy/setup.bash" >> /root/.bashrc
RUN echo "export PYTHONPATH=/workspace:\$PYTHONPATH" >> /root/.bashrc

CMD ["/bin/bash"]
