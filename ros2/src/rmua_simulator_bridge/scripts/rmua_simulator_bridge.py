#!/usr/bin/env python3
"""ROS 2 Humble adapter for the upstream ROS 1 simulator via rosbridge v2."""
import base64
import json
import threading
import uuid
from pathlib import Path

import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
from rosidl_runtime_py.convert import message_to_ordereddict
from rosidl_runtime_py.set_message import set_message_fields
from rosidl_runtime_py.utilities import get_message, get_service
import websocket
import yaml
from ament_index_python.packages import get_package_share_directory

LEGACY_FIELDS = {
    'yawRate': 'yaw_rate', 'rollRate': 'roll_rate', 'pitchRate': 'pitch_rate',
    'rotorPWM0': 'rotor_pwm0', 'rotorPWM1': 'rotor_pwm1',
    'rotorPWM2': 'rotor_pwm2', 'rotorPWM3': 'rotor_pwm3',
    'waitOnLastTask': 'wait_on_last_task',
}
ROS1_FIELDS = {v: k for k, v in LEGACY_FIELDS.items()}


def to_ros2(value):
    if isinstance(value, list):
        return [to_ros2(v) for v in value]
    if not isinstance(value, dict):
        return value
    if 'secs' in value and 'nsecs' in value:
        return {'sec': value['secs'], 'nanosec': value['nsecs']}
    result = {LEGACY_FIELDS.get(k, k): to_ros2(v) for k, v in value.items() if k != 'seq'}
    # rosbridge encodes uint8[] as base64, notably Image and PointCloud2.data.
    if isinstance(result.get('data'), str):
        result['data'] = list(base64.b64decode(result['data'], validate=True))
    return result


def to_ros1(value):
    if isinstance(value, (list, tuple)):
        return [to_ros1(v) for v in value]
    if not isinstance(value, dict):
        return value
    if 'sec' in value and 'nanosec' in value:
        return {'secs': value['sec'], 'nsecs': value['nanosec']}
    result = {ROS1_FIELDS.get(k, k): to_ros1(v) for k, v in value.items()}
    if 'stamp' in result and 'frame_id' in result:
        result['seq'] = 0
    return result


class SimulatorBridge(Node):
    def __init__(self):
        super().__init__('rmua_simulator_bridge')
        default = Path(get_package_share_directory('rmua_simulator_bridge')) / 'config/topics.yaml'
        self.declare_parameter('config_file', str(default))
        self.declare_parameter('url', 'ws://127.0.0.1:9090')
        self.declare_parameter('service_timeout', 10.0)
        with open(self.get_parameter('config_file').value, encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        self.socket = None
        self.lock = threading.RLock()
        self.pending = {}
        self.stopping = threading.Event()
        self.connected = threading.Event()
        self.telemetry = {}
        self.handles = []
        self.service_group = ReentrantCallbackGroup()
        for spec in self.config['telemetry']:
            cls = get_message(spec['type'])
            qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.TRANSIENT_LOCAL if spec.get('retained') else DurabilityPolicy.VOLATILE)
            self.telemetry[spec['topic']] = (cls, self.create_publisher(cls, spec['topic'], qos))
        for spec in self.config['commands']:
            cls = get_message(spec['type'])
            self.handles.append(self.create_subscription(cls, spec['topic'],
                lambda msg, topic=spec['topic']: self.command(topic, msg), 10))
        for spec in self.config['services']:
            cls = get_service(spec['type'])
            self.handles.append(self.create_service(cls, spec['name'],
                lambda req, res, name=spec['name']: self.service(name, req, res),
                callback_group=self.service_group))
        self.worker = threading.Thread(target=self.receive, name='rosbridge-receiver', daemon=True)
        self.worker.start()

    def send(self, packet):
        with self.lock:
            if self.socket is None or not self.connected.is_set():
                raise ConnectionError('simulator rosbridge is disconnected')
            self.socket.send(json.dumps(packet))

    def command(self, topic, msg):
        try:
            self.send({'op': 'publish', 'topic': topic, 'msg': to_ros1(message_to_ordereddict(msg))})
        except (ConnectionError, OSError, websocket.WebSocketException) as exc:
            self.get_logger().warning(f'Command dropped ({topic}): {exc}', throttle_duration_sec=5)

    def service(self, name, request, response):
        call_id = uuid.uuid4().hex
        event, result = threading.Event(), {}
        try:
            with self.lock:
                self.pending[call_id] = (event, result)
            self.send({'op': 'call_service', 'id': call_id, 'service': name,
                       'args': to_ros1(message_to_ordereddict(request))})
            if not event.wait(float(self.get_parameter('service_timeout').value)):
                raise TimeoutError(f'{name} timed out')
            if not result.get('result', False):
                raise RuntimeError(str(result.get('values', 'transport disconnected')))
            set_message_fields(response, to_ros2(result.get('values', {})))
        except Exception as exc:
            self.get_logger().error(f'Service {name}: {exc}')
            if hasattr(response, 'success'):
                response.success = False
            if hasattr(response, 'message'):
                response.message = str(exc)
        finally:
            with self.lock:
                self.pending.pop(call_id, None)
        return response

    def receive(self):
        while not self.stopping.is_set():
            sock = None
            try:
                sock = websocket.create_connection(self.get_parameter('url').value, timeout=2,
                                                     enable_multithread=True)
                sock.settimeout(1)
                with self.lock:
                    self.socket = sock
                    self.connected.set()
                    for spec in self.config['commands']:
                        self.send({'op': 'advertise', 'topic': spec['topic'],
                                   'type': spec['type'].replace('/msg/', '/')})
                    for spec in self.config['telemetry']:
                        self.send({'op': 'subscribe', 'topic': spec['topic'],
                                   'type': spec['type'].replace('/msg/', '/'),
                                   'queue_length': 1})
                self.get_logger().info('Connected to simulator rosbridge')
                while not self.stopping.is_set():
                    try:
                        raw = sock.recv()
                    except websocket.WebSocketTimeoutException:
                        continue
                    if not raw:
                        raise ConnectionError('connection closed')
                    packet = json.loads(raw)
                    if packet.get('op') == 'publish' and packet.get('topic') in self.telemetry:
                        try:
                            cls, publisher = self.telemetry[packet['topic']]
                            msg = cls()
                            set_message_fields(msg, to_ros2(packet['msg']))
                            publisher.publish(msg)
                        except Exception as exc:
                            self.get_logger().error(f'Message {packet.get("topic")}: {exc}', throttle_duration_sec=5)
                    elif packet.get('op') == 'service_response':
                        with self.lock:
                            pending = self.pending.get(packet.get('id'))
                            if pending:
                                pending[1].update(packet)
                                pending[0].set()
                    elif packet.get('op') == 'status' and packet.get('level') == 'error':
                        self.get_logger().error(f'rosbridge: {packet.get("msg")}')
            except Exception as exc:
                if not self.stopping.is_set():
                    self.get_logger().warning(f'Waiting for simulator: {exc}', throttle_duration_sec=5)
            finally:
                with self.lock:
                    self.connected.clear()
                    self.socket = None
                    for event, result in self.pending.values():
                        result.update(result=False, values='transport disconnected')
                        event.set()
                if sock:
                    sock.close()
            self.stopping.wait(2)

    def close(self):
        self.stopping.set()
        with self.lock:
            if self.socket:
                self.socket.close()
        self.worker.join(timeout=4)


def main():
    rclpy.init()
    node = SimulatorBridge()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try:
        executor.spin()
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    finally:
        node.close()
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
