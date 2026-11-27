from setuptools import setup
import os
from glob import glob

package_name = 'nav'

setup(
    name=package_name,
    version='0.2.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'),
            glob('launch/*.launch.py')),
        (os.path.join('share', package_name, 'config'),
            glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='anmol',
    maintainer_email='anmol@slam.local',
    description='Nav2 navigation + serial bridge for the mecanum robot (forward + pivot only)',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'cmd_vel_bridge = nav.cmd_vel_bridge:main',
            'navigate_to = nav.navigate_to:main',
        ],
    },
)
