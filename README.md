# RMUA2026 — ROS 2 Humble 适配（ysy）

宿主机：Ubuntu 22.04 / ROS 2 Humble。原版资料见 [README_ROS1.md](README_ROS1.md)。

**这个仓库没有 Unreal/AirSim 引擎源码。** 官方下载的是 ROS 1 Noetic 二进制，因此这里采用：

```text
Humble 开发节点 ⇄ ROS 2 rmua_simulator_bridge ⇄ localhost WebSocket
              ⇄ Noetic rosbridge ⇄ 官方 Unreal 模拟器
```

开发节点和接口已经迁移到原生 ROS 2；闭源引擎通过适配层连接。没有将引擎二进制伪称为原生 ROS 2。
图像/点云通过 rosbridge JSON/base64 传输，带宽和延迟大于原生 DDS；高帧率多相机需实测性能。

日常启动、停止、参数和故障处理见 [操作说明](docs/OPERATIONS.md)；首次系统配置见 [Base 环境说明](../IntelligentUAVChampionshipBase/docs/ENVIRONMENT.md)。

## 1. 构建 ROS 2 工作区

将 Base 仓库与本仓库并排放置：

```text
UAV/
  IntelligentUAVChampionshipBase/
  IntelligentUAVChampionshipSimulator/
```

```bash
export UAV_ROOT=/home/pk620/桌面/UAV  # 其他机器请修改此路径
cd "$UAV_ROOT/IntelligentUAVChampionshipBase/basic_dev"
./scripts/setup_venv.sh
./build_ros2.sh
source env_ros2.bash
```

适配层依赖系统 Python 的 `websocket-client` 和 PyYAML：

```bash
sudo apt install python3-websocket python3-yaml
```

项目 `.venv` 中安装 websocket-client；启动脚本会加载它。构建工具和依赖安装脚本见 Base README。
构建产物位于 `$HOME/.cache/rmua2026-ros2`，避开中文路径的 Humble rosidl 问题。

## 2. 构建引擎容器

需要 Docker、NVIDIA 驱动及 NVIDIA Container Toolkit。宿主机不需要安装 Noetic。

```bash
cd "$UAV_ROOT/IntelligentUAVChampionshipSimulator"
./build_simulator.sh
```

镜像固定使用 Ubuntu 20.04 Unreal runtime，安装 Noetic、rosbridge 及原始消息定义。
构建脚本并行下载官方 `simulator_12.0.0.5.zip`、构建兼容运行环境，缓存位于
`$HOME/.cache/rmua2026-assets`；引擎通过分段断点缓存下载，并校验 ZIP 全部条目的 CRC。
可用 `SIMULATOR_URL=... ./build_simulator.sh` 指定同版本压缩包地址，`SIM_DOWNLOAD_WORKERS`
调整下载并发数（默认 32），`SIM_ASSET_CACHE` 修改缓存路径。APT 依赖也进行并行预取，仍由
APT 验证仓库签名、包哈希并安装。默认 HTTPS 中科大镜像，
可用 `--build-arg UBUNTU_MIRROR=... --build-arg ROS1_MIRROR=...` 覆盖。
构建脚本通过 BuildKit 传入宿主机 CA 证书以引导最小镜像的 HTTPS，保留 TLS 验证。

## 3. 启动

```bash
cd "$UAV_ROOT/IntelligentUAVChampionshipSimulator"
export ROS_DOMAIN_ID=20  # 各终端保持一致
# 以下启动方式二选一；123 为随机种子
# 自动启动引擎容器和 ROS 2 适配层
./run_simulator_offscreen.sh 123
# 有窗口模式，需要可用的 DISPLAY/Xauthority
./run_simulator.sh 123
```

也可分开启动，便于调试：

```bash
./run_docker_simulator.sh 123
# 另一个终端
./run_ros2_bridge.sh
# 再一个终端
source ../IntelligentUAVChampionshipBase/basic_dev/env_ros2.bash
ros2 topic list
ros2 topic echo /airsim_node/drone_1/imu/imu --once --qos-reliability best_effort
```

已有远程或自建 ROS 1 rosbridge 端点时，可单独运行：

```bash
./run_ros2_bridge.sh url:=ws://127.0.0.1:9090
```

所有 ROS 2 进程保持相同 `ROS_DOMAIN_ID`。脚本沿用宿主机现有值，本机为 20；
ROS 1 的 ROS_MASTER_URI/ROS_IP 不用于 ROS 2。适配层默认连接 `127.0.0.1:9090`。
`SIM_IMAGE`、`SIM_CONTAINER_NAME`、`SIM_GPUS`、`ROSBRIDGE_PORT` 可通过环境变量覆盖；
若更换端口，独立运行适配层时同时传入对应的 `url`。

## 接口与配置

`ros2/src/rmua_simulator_bridge/config/topics.yaml` 显式列出适配方向和类型：

- ROS 1 → ROS 2：四路相机、IMU、GPS、点云、真值位姿、电机状态、初始位姿、终点。
- ROS 2 → ROS 1：`/airsim_node/drone_1/vel_body_cmd` 和 `rotor_pwm_cmd`。
- 服务：`drone_1/takeoff`、`drone_1/land`、`reset`、`meter_report`。

初始位姿和终点使用 transient_local；时间戳保持模拟器值，不用主机接收时间覆盖，也不虚构 `/clock`。
自定义字段和 ROS 1/2 时间字段由适配器转换；断线自动重连并恢复订阅，不重放旧飞行指令。
服务超时/断线返回 `success=false` 并输出错误日志。

2026 VelCmd 字段为 `header, vx, vy, vz, yaw_rate, va, stop`，详见 Base README。
`VelCmdmsg/VelCmd.msg` 和 `ros1_interfaces` 保留官方 ROS 1 字段名用于二进制通信。

`meter_report` 的接口已通过官方 12.0.0.5 引擎库中的服务 MD5 核对：请求为
`int64 index, int64 value`，响应为 `bool success`，MD5 为
`40e1aa17dd96ff6a8c88396581d6a491`。风速调试话题已在实际引擎中核对为 `geometry_msgs/Vector3Stamped`，当前未加入默认适配配置。
其他已有服务类型也可按 YAML 配置加入适配，前提是引擎实际提供该服务。

## 验证范围

已在本机 Ubuntu 22.04 / Humble / RTX 4090 环境完成：

- 七个 ROS 2 包构建，以及模拟 rosbridge 双向通信、服务、重连和原生节点的三项集成测试。
- Docker、Compose、Buildx、NVIDIA Container Toolkit 安装及 GPU 容器检查。
- 官方 12.0.0.5 引擎下载、ZIP 全条目 CRC 校验和完整仿真镜像构建。
- 种子 123 的真实 1280×720 图形场景启动，ROS 2 接收到 960×720 前视图像、IMU 和初始位姿。
- VelCmd、RotorPWM、Takeoff、Land、Reset、MeterReport 的 ROS 1 MD5 与官方引擎库一致，
  容器构建时还会实际导入生成的 Python 接口并断言关键 MD5，防止接口包被忽略。

尚未进行完整竞速飞行闭环、长时间性能或全部服务的实际调用测试。

参考：[rosbridge 协议](https://github.com/RobotWebTools/rosbridge_suite/blob/ros1/ROSBRIDGE_PROTOCOL.md)、
[Unreal runtime 镜像](https://github.com/adamrehn/ue4-runtime)。
