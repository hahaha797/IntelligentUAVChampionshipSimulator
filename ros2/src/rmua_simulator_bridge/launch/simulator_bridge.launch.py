from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('url', default_value='ws://127.0.0.1:9090'),
        Node(package='rmua_simulator_bridge', executable='rmua_simulator_bridge',
             output='screen', parameters=[{'url': LaunchConfiguration('url')}]),
    ])
