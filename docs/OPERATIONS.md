# 仿真操作与故障处理

前提：已完成 [Base 环境配置](../../IntelligentUAVChampionshipBase/docs/ENVIRONMENT.md)，ROS 2 工作区及仿真镜像均已构建。
以下命令在宿主机 Bash 执行，路径对应当前机器；迁移目录后修改 `UAV_ROOT`。

## 启动与停止

```bash
export UAV_ROOT=/home/pk620/桌面/UAV
export ROS_DOMAIN_ID=20
cd "$UAV_ROOT/IntelligentUAVChampionshipSimulator"
./run_simulator.sh 123
```

`123` 是随机种子，省略时也使用 123。此命令启动图形引擎容器和 ROS 2 适配层；在同一终端按 `Ctrl-C` 会清理两者。
界面显示无人机在停机坪、`Pending` 时，表示仿真处于等待状态。控制器需另行启动，基础观察节点不会自动起飞。

无窗口运行使用 `./run_simulator_offscreen.sh 123`，仍需 GPU 和 NVIDIA 容器运行时。
默认容器名为 `sim01`，不要同时重复启动同名实例。停止当前实例也可运行：

```bash
docker stop sim01
```

容器带有 `--rm`，退出后自动删除，镜像和宿主机下载缓存保留。分开启动引擎和适配层时，二者需分别停止。

## 分开调试

每个终端先设置相同的 `UAV_ROOT` 和 `ROS_DOMAIN_ID`，再进入 Simulator 目录。

```bash
# 终端 1：只启动引擎；添加 SIM_RENDER=1 可显示窗口
./run_docker_simulator.sh 123
```

```bash
# 终端 2：只启动适配层，脚本自动加载项目 ROS 2 环境
./run_ros2_bridge.sh url:=ws://127.0.0.1:9090
```

```bash
# 终端 3：观察 ROS 2 数据
source "$UAV_ROOT/IntelligentUAVChampionshipBase/basic_dev/env_ros2.bash"
ros2 node list
ros2 topic list -t
ros2 topic echo /airsim_node/drone_1/imu/imu --once --qos-reliability best_effort
ros2 topic info /airsim_node/drone_1/front_left/Scene --verbose
ros2 run basic_dev basic_dev
```

最后一条命令运行传感器观察示例；`Ctrl-C` 退出该节点。不要通过 `ros2 topic echo` 持续打印完整图像字节来判断画面是否正常。

## 脚本与参数

| 入口 | 作用 |
| --- | --- |
| `build_simulator.sh` | 并行准备运行环境和引擎下载，再构建完整镜像 |
| `run_simulator.sh [seed]` | 图形引擎 + ROS 2 适配层 |
| `run_simulator_offscreen.sh [seed]` | 引擎 + ROS 2 适配层，默认离屏 |
| `run_docker_simulator.sh [seed]` | 仅启动引擎容器 |
| `run_ros2_bridge.sh [url:=...]` | 仅启动 ROS 2 适配层 |
| `start.bash` | 容器内部启动 roscore、rosbridge 和引擎 |

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `SIM_IMAGE` | `simulator01:humble-adapter` | 完整仿真镜像，构建与运行应一致 |
| `SIM_RUNTIME_IMAGE` | `simulator01:runtime` | 构建中间运行环境的标签，不是完整引擎镜像 |
| `SIM_CONTAINER_NAME` | `sim01` | 容器名及清理目标 |
| `SIM_GPUS` | `all` | 传递给 Docker `--gpus` |
| `SIM_RENDER` | `0` | 直接运行离屏/容器脚本时的显示开关；图形脚本固定设为 1 |
| `ROSBRIDGE_PORT` | `9090` | 容器 rosbridge 端口，一体启动脚本同步适配层 URL |
| `SIM_ASSET_CACHE` | `$HOME/.cache/rmua2026-assets` | 官方引擎下载缓存 |
| `SIM_DOWNLOAD_WORKERS` | `32` | 引擎分段下载并发 |
| `SIMULATOR_URL` | 脚本内官方 12.0.0.5 地址 | 替换同版本引擎下载源 |
| `UAV_ROS2_CACHE` | `$HOME/.cache/rmua2026-ros2` | ROS 2 构建和运行共用的英文缓存路径 |

更换端口示例：

```bash
ROSBRIDGE_PORT=9091 ./run_simulator.sh 123
# 若分开启动适配层，需手动匹配 URL：
# ./run_ros2_bridge.sh url:=ws://127.0.0.1:9091
```

容器使用 host 网络；更改容器名并不能隔离 ROS 1 master、引擎和 rosbridge 的网络端口，不建议直接并行运行多套实例。
适配层默认连接 localhost。本次 Noetic rosbridge 实测监听 `0.0.0.0:9090`，不能将该配置理解为端口只绑定回环地址。

## 构建与下载缓存

```bash
cd "$UAV_ROOT/IntelligentUAVChampionshipSimulator"
./build_simulator.sh
```

默认下载 `simulator_12.0.0.5.zip`（2,021,176,468 字节）。下载器缓存已完成分段，失败后重新运行同一命令可复用缓存；完成后组合 ZIP 并检查所有条目的 CRC。
`engine.json` 记录下载源、大小和 ETag。CRC 校验用于检查压缩包完整性，不是发布方数字签名验证。
缓存不放入 Git；切勿只复制源码后认为大型引擎资源也已包含在仓库中。

默认使用 HTTPS 中科大 Ubuntu/ROS 镜像。需要调整时：

```bash
./build_simulator.sh \
  --build-arg UBUNTU_MIRROR=https://mirrors.ustc.edu.cn/ubuntu \
  --build-arg ROS1_MIRROR=https://mirrors.ustc.edu.cn/ros/ubuntu
```

构建需要 Docker BuildKit/Buildx，使用命名构建上下文和宿主机 CA secret；仅直接运行 `docker build .` 不能替代包装脚本。
APT 并行预取后仍由 APT 校验仓库签名和包哈希。可用 `SIM_DOWNLOAD_WORKERS=8 ./build_simulator.sh` 降低下载并发。

## 接口配置与开发边界

默认映射以 [topics.yaml](../ros2/src/rmua_simulator_bridge/config/topics.yaml) 为准：

| 方向 | 内容 | QoS / 行为 |
| --- | --- | --- |
| ROS 1 → ROS 2 | 四路 Scene 图像 | 发布端 Reliable，深度 1；Base 图像订阅深度 2 |
| ROS 1 → ROS 2 | IMU、GPS、点云等传感器 | 发布端 Reliable，深度 1；Base 使用 SensorDataQoS 订阅 |
| ROS 1 → ROS 2 | 初始位姿、终点 | transient_local，后启动订阅者可获取保留值 |
| ROS 2 → ROS 1 | VelCmd、RotorPWM | 断线期间不重放旧指令 |
| ROS 2 服务 → ROS 1 | takeoff、land、reset、meter_report | 超时或断线返回失败 |

服务名及类型可用 `ros2 service list -t` 查看；数据定义可用 `ros2 interface show airsim_ros/srv/MeterReport` 查看，无需实际调用服务。
服务等待超时默认 10 秒；默认 launch 仅暴露 `url` 参数。需要自定义 YAML 或超时时，可直接运行节点：

```bash
source "$UAV_ROOT/IntelligentUAVChampionshipBase/basic_dev/env_ros2.bash"
ros2 run rmua_simulator_bridge rmua_simulator_bridge --ros-args \
  -p url:=ws://127.0.0.1:9090 \
  -p config_file:="$UAV_ROOT/IntelligentUAVChampionshipSimulator/ros2/src/rmua_simulator_bridge/config/topics.yaml" \
  -p service_timeout:=10.0
```

运行此命令前先停止已有适配层，避免重复发布或重复转发控制指令。
相机 CameraInfo 和风速调试话题没有加入默认映射；引擎提供某话题不等于 ROS 2 已经转发它。
时间戳及 NED 坐标保持引擎语义；当前没有 `/clock`，不要仅为运行仿真而设置 `use_sim_time=true`。

## 日志与诊断

```bash
docker ps --filter name=sim01
docker logs --tail 100 sim01
# 查看容器内部 ROS 1 话题，命令仅用于诊断
docker exec sim01 bash -lc 'source /opt/ros/noetic/setup.bash; source /bridge_ws/devel/setup.bash; rostopic list'
```

`docker logs` 只包含容器侧输出；宿主机 ROS 2 适配层日志在启动终端和 ROS 日志目录。
需要为下一次启动保存完整输出，可使用：

```bash
set -o pipefail
./run_simulator.sh 123 2>&1 | tee "$HOME/uav-simulator-runtime.log"
```

本次会话已有 `/tmp/uav-simulator-runtime.log` 和 `/tmp/uav-simulator-build.log`；临时文件可能在重启后消失。

| 现象 | 处理方式 |
| --- | --- |
| 容器名 `sim01` 已被占用 | 先用 `docker ps -a` 确认现有实例；继续使用它，或正常停止后再启动。 |
| DISPLAY 未设置、X11 cookie 为空、窗口打不开 | 从当前桌面会话的终端运行，检查 `echo "$DISPLAY"` 和 `xauth list`；脚本会生成容器可用的 Xauthority。无需显示时用离屏脚本。 |
| 适配层反复连接失败 | 检查容器是否仍运行、rosbridge 日志及端口；独立启动时核对 `url`。引擎初次启动期间可等待自动重连。 |
| 有话题但没有图像 | 检查引擎侧图像话题、适配层连接和 `ros2 topic info --verbose`；当前图像采用 Reliable，避免本机大图像分片丢失问题。 |
| 初始位姿晚订阅时收不到 | 自定义订阅者需使用 transient_local；普通易失订阅不会获得旧的保留消息。 |
| ROS 1 提示自定义类型不匹配 | 核对 ROS 1 MD5；不要将 ROS 2 snake_case 定义直接复制进兼容包。修改接口后重建 ROS 2 工作区和仿真镜像。 |
| catkin 构建成功但缺少 airsim_ros | `COLCON_IGNORE` 应在 `ros1_interfaces` 父目录，不能放入被 COPY 的 `airsim_ros` 包内；镜像构建已增加 Python 导入与 MD5 断言。 |
| 源码路径改变后加载旧包 | 使用新的英文 `UAV_ROS2_CACHE` 重建，随后在所有启动终端使用相同变量。 |

真实图形场景和图像/IMU/初始位姿接收已经验证；这些检查不代表控制器飞行精度、所有服务或完整竞速闭环已经验证。
