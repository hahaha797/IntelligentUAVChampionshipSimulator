# The upstream Unreal binary speaks ROS 1; keep it isolated from the Humble host.
FROM adamrehn/ue4-runtime:20.04-vulkan-noaudio AS runtime
USER root
ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 LC_ALL=C.UTF-8 ROS_DISTRO=noetic
RUN test "$(. /etc/os-release && echo "$VERSION_CODENAME")" = focal
ARG UBUNTU_MIRROR=https://mirrors.ustc.edu.cn/ubuntu
ARG ROS1_MIRROR=https://mirrors.ustc.edu.cn/ros/ubuntu
COPY scripts/apt_parallel_install.sh /usr/local/sbin/apt-parallel-install
RUN --mount=type=secret,id=bootstrap_ca,target=/tmp/bootstrap-ca.crt \
    --mount=type=cache,target=/var/lib/apt/lists \
    --mount=type=cache,target=/var/cache/apt/archives \
    mkdir -p /etc/ssl/certs && \
    if [ -f /tmp/bootstrap-ca.crt ]; then cp /tmp/bootstrap-ca.crt /etc/ssl/certs/ca-certificates.crt && chmod 644 /etc/ssl/certs/ca-certificates.crt; fi && \
    sed -i "s@http://archive.ubuntu.com/ubuntu@${UBUNTU_MIRROR}@g; s@http://security.ubuntu.com/ubuntu@${UBUNTU_MIRROR}@g" /etc/apt/sources.list && \
    printf 'Acquire::https::CaInfo "/etc/ssl/certs/ca-certificates.crt";\nAcquire::ForceIPv4 "true";\nAcquire::Retries "3";\n' > /etc/apt/apt.conf.d/99uav-network && \
    rm -f /etc/apt/apt.conf.d/docker-clean && \
    apt-get update && apt-parallel-install ca-certificates curl gnupg2 unzip
RUN --mount=type=cache,target=/var/lib/apt/lists \
    --mount=type=cache,target=/var/cache/apt/archives \
    curl -fsSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.asc \
      | gpg --dearmor -o /usr/share/keyrings/ros-archive-keyring.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] ${ROS1_MIRROR} focal main" \
      > /etc/apt/sources.list.d/ros1.list && \
    apt-get update && apt-parallel-install ffmpeg ros-noetic-ros-base \
      ros-noetic-rosbridge-server ros-noetic-geographic-msgs build-essential
COPY ros1_interfaces/airsim_ros /bridge_ws/src/airsim_ros
RUN . /opt/ros/noetic/setup.sh && cd /bridge_ws && catkin_make && \
    . devel/setup.sh && python3 -c "from airsim_ros.msg import VelCmd, RotorPWM; from airsim_ros.srv import MeterReport; assert VelCmd._md5sum == '1a888a503939ba521aed68feee8eab6d'; assert RotorPWM._md5sum == '4967432b608c06d70b17be20124fa258'; assert MeterReport._md5sum == '40e1aa17dd96ff6a8c88396581d6a491'"
FROM runtime AS simulator
# The helper downloads and verifies the official archive into a reusable host cache.
RUN --mount=type=bind,from=engine_archive,source=simulator_12.0.0.5.zip,target=/tmp/simulator.zip,readonly \
    unzip -q /tmp/simulator.zip -d /tmp/simulator && \
    simulator_dir="$(find /tmp/simulator -type d -name LinuxNoEditor -print -quit)" && \
    test -n "$simulator_dir" && mv "$simulator_dir" /usr/local/LinuxNoEditor && \
    rm -rf /tmp/simulator && \
    chmod +x /usr/local/LinuxNoEditor/RMUA.sh \
      /usr/local/LinuxNoEditor/RMUA/Binaries/Linux/RMUA-Linux-Shipping && \
    chown -R ue4:ue4 /usr/local/LinuxNoEditor
COPY settings.json /usr/local/LinuxNoEditor/RMUA/Binaries/Linux/settings.json
COPY start.bash /usr/local/start.bash
RUN chmod +x /usr/local/start.bash && chown -R ue4:ue4 /bridge_ws
USER ue4
ENTRYPOINT ["/usr/local/start.bash"]
