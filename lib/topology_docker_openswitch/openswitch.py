# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2016 Hewlett Packard Enterprise Development LP
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

"""
Custom Topology Docker Node for OpenSwitch.

    http://openswitch.net/
"""

from __future__ import unicode_literals, absolute_import
from __future__ import print_function, division

from json import loads
from subprocess import check_output, CalledProcessError
from platform import system, linux_distribution
from logging import StreamHandler, getLogger, INFO, Formatter
from sys import stdout
from os.path import join, dirname, normpath, abspath

from topology_docker.node import DockerNode
from topology_docker_openswitch.connection import OpenswitchSSHConnection
from topology_docker_openswitch.shell import (
    OpenSwitchVtyshShell,
    OpenSwitchBashShell,
    OpenSwitchBashSwnsShell,
    OpenSwitchVsctlShell
)


# When a failure happens during boot time, logs and other information is
# collected to help with the debugging. The path of this collection is to be
# stored here at module level to be able to import it in the pytest teardown
# hook later. Non-failing containers will append their log paths here also.
LOG_PATHS = []
LOG = getLogger(__name__)
LOG_HDLR = StreamHandler(stream=stdout)
LOG_HDLR.setFormatter(Formatter('%(asctime)s %(message)s'))
LOG_HDLR.setLevel(INFO)
LOG.addHandler(LOG_HDLR)
LOG.setLevel(INFO)


def log_commands(
    commands, location, function, escape=True,
    prefix=None, suffix=None, **kwargs
):
    if prefix is None:
        prefix = ''
    if suffix is None:
        suffix = ''

    for command in commands:
        log_path = ' >> {} 2>&1'.format(location)
        args = [
            r'{prefix}echo \"Output of:'
            r' {command}{log_path}\"{log_path}{suffix}'.format(
                prefix=prefix, command=command,
                log_path=log_path, suffix=suffix
            ),
            r'{}{}{}{}'.format(
                prefix, command, log_path, suffix
            ),
            r'{}echo \"\"{}{}'.format(prefix, log_path, suffix)
        ]

        for arg in args:
            try:
                if not escape:
                    arg = arg.replace('\\', '')
                function(arg, **kwargs)

            except CalledProcessError as error:
                LOG.warning(
                    '{} failed with error {}.'.format(
                        command, error.returncode
                    )
                )


class OpenSwitchNode(DockerNode):
    """
    Custom OpenSwitch node for the Topology Docker platform engine.
    This custom node loads an OpenSwitch image and has vtysh as default
    shell (in addition to bash).
    See :class:`topology_docker.node.DockerNode`.
    """

    def __init__(
            self, identifier,
            image='topology/ops:latest', binds=None,
            environment={'container': 'docker'},
            **kwargs):

        # Add binded directories
        container_binds = [
            '/dev/log:/dev/log',
            '/sys/fs/cgroup:/sys/fs/cgroup'
        ]
        if binds is not None:
            container_binds.append(binds)

        super(OpenSwitchNode, self).__init__(
            identifier, image=image, command='/sbin/init',
            binds=';'.join(container_binds), hostname='switch',
            network_mode='bridge', environment={'container': 'docker'},
            **kwargs
        )

        self._register_connection_type('ssh', OpenswitchSSHConnection)

        # FIXME: Remove this attribute to merge with version > 1.6.0
        self.shared_dir_mount = '/tmp'

    @property
    def default_connection(self):
        return super(OpenSwitchNode, self.__class__).default_connection

    @default_connection.setter
    def default_connection(self, connection):
        """
        See :meth:`ConnectionAPI.default_connection` for more information.

        penswitch nodes support only one "console" connection,
        this is done to keep behavior consistent with physical hardware
        so this makes sure that only the '0' connection is used always.
        """

        if connection != '0':
            raise Exception('Only one telnet connection is available.')

        super(OpenSwitchNode, self.__class__).default_connection.fset(
            self, connection
        )

    def connect(self, connection=None, connection_type=None,
                via_node=None, **kwargs):
        """
        See :meth:`ConnectionAPI.connect` for more information.

        Openswitch nodes support only one "console" connection,
        this is done to keep behavior consistent with physical hardware
        so this makes sure that only the '0' connection is used always.
        """

        connection_type = connection_type or self._default_connection_type

        if connection_type is "docker":
            if connection is not None and connection != '0':
                raise Exception('Only one "console" connection is available.')

        super(OpenSwitchNode, self).connect(
            connection=connection, connection_type=connection_type,
            via_node=via_node, **kwargs
        )

    def _register_shells(self, connectionobj):
        """
        See :meth:`CommonNode._register_shells` for more information.
        """
        connectionobj._register_shell('vtysh', OpenSwitchVtyshShell())
        connectionobj._register_shell('bash', OpenSwitchBashShell())
        connectionobj._register_shell('bash_swns', OpenSwitchBashSwnsShell())
        connectionobj._register_shell('vsctl', OpenSwitchVsctlShell())

    def notify_post_build(self):
        """
        Get notified that the post build stage of the topology build was
        reached.

        See :meth:`DockerNode.notify_post_build` for more information.
        """
        super(OpenSwitchNode, self).notify_post_build()
        self._setup_system()

    def _setup_system(self):
        """
        Setup the OpenSwitch image for testing.

        #. Wait for daemons to converge.
        #. Assign an interface to each port label.
        #. Create remaining interfaces.
        """

        # Write and execute setup script
        with open(
            join(dirname(normpath(abspath(__file__))), 'openswitch_setup')
        ) as openswitch_setup_file:
            openswitch_setup = openswitch_setup_file.read()

        setup_script = '{}/openswitch_setup.py'.format(self.shared_dir)
        with open(setup_script, 'w') as fd:
            fd.write(openswitch_setup)

        try:
            self._docker_exec(
                'python {}/openswitch_setup.py -d'.format(
                    self.shared_dir_mount
                )
            )
        except Exception as e:
            global FAIL_LOG_PATH
            lines_to_dump = 100

            platforms_log_location = {
                'Ubuntu': 'cat /var/log/upstart/docker.log',
                'CentOS Linux': 'grep docker /var/log/daemon.log',
                'debian': 'journalctl -u docker.service',
                # FIXME: find the right values for the next dictionary keys:
                # 'boot2docker': 'cat /var/log/docker.log',
                # 'debian': 'cat /var/log/daemon.log',
                # 'fedora': 'journalctl -u docker.service',
                # 'red hat': 'grep docker /var/log/messages',
                # 'opensuse': 'journalctl -u docker.service'
            }

            # Here, we find the command to dump the last "lines_to_dump" lines
            # of the docker log file in the logs. The location of the docker
            # log file depends on the Linux distribution. These locations are
            # defined the in "platforms_log_location" dictionary.

            operating_system = system()

            if operating_system != 'Linux':
                LOG.warning(
                    'Operating system is not Linux but {}.'.format(
                        operating_system
                    )
                )
                return

            linux_distro = linux_distribution()[0]

            if linux_distro not in platforms_log_location.keys():
                LOG.warning(
                    'Unknown Linux distribution {}.'.format(
                        linux_distro
                    )
                )

            docker_log_command = '{} | tail -n {}'.format(
                platforms_log_location[linux_distro], lines_to_dump
            )

            container_commands = [
                'ovs-vsctl list Daemon',
                'coredumpctl gdb',
                'ps -aef',
                'systemctl status',
                'systemctl --state=failed --all',
                'ovsdb-client dump',
                'systemctl status switchd -n 10000 -l',
                'cat /var/log/messages'
            ]

            execution_machine_commands = [
                'tail -n 2000 /var/log/syslog',
                'docker ps -a',
                docker_log_command
            ]

            log_commands(
                container_commands,
                '{}/container_logs'.format(self.shared_dir_mount),
                self._docker_exec,
                prefix=r'sh -c "',
                suffix=r'"'
            )
            log_commands(
                execution_machine_commands,
                '{}/execution_machine_logs'.format(self.shared_dir),
                check_output,
                escape=False,
                shell=True
            )
            LOG_PATHS.append(self.shared_dir)

            raise e
        # Read back port mapping
        port_mapping = '{}/port_mapping.json'.format(self.shared_dir)
        with open(port_mapping, 'r') as fd:
            mappings = loads(fd.read())

        LOG_PATHS.append(self.shared_dir)

        if hasattr(self, 'ports'):
            self.ports.update(mappings)
            return
        self.ports = mappings

    def set_port_state(self, portlbl, state):
        """
        Set the given port label to the given state.

        See :meth:`DockerNode.set_port_state` for more information.
        """
        iface = self.ports[portlbl]
        state = 'up' if state else 'down'

        not_in_netns = self._docker_exec('ls /sys/class/net/').split()
        prefix = '' if iface in not_in_netns else 'ip netns exec swns'

        command = '{prefix} ip link set dev {iface} {state}'.format(**locals())
        self._docker_exec(command)

    def stop(self):
        """
        See :meth:`topology_docker.node.DockerNode.stop` for more information.

        This method exits and stops the container.
        """

        for connection in self.available_connections():
            conn = self.get_connection(connection=connection)
            conn.get_shell('bash')._exit()
        super(OpenSwitchNode, self).stop()


__all__ = ['OpenSwitchNode']
