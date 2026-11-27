from glob import glob
from setuptools import setup, find_packages

package_name = 'localization_node'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', glob('launch/*.py')),
        ('share/' + package_name + '/config', glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='robot-team',
    maintainer_email='you@example.com',
    description='Map server + AMCL with checkpoint-based start pose',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'localize = localization_node.localize:main',
        ],
    },
)
