# -*- coding: utf-8 -*-
#
# Copyright (C) 2015 Hewlett Packard Enterprise Development LP <asicapi@hp.com>
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

from os import environ

from topology_docker.platform import DockerNode

from ..shell import DockerShell


class OpenSwitchNode(DockerNode):
    """
    """

    def __init__(
            self, identifier,
            image='ops:latest', command='/sbin/init', binds=None,
            **kwargs):

        # Fetch image from environment
        image = environ.get('OPS_IMAGE', image)

        # Add binded directories
        if binds is None:
            binds = []
        binds.extend([
            '/tmp:/tmp',
            '/dev/log:/dev/log',
            '/sys/fs/cgroup:/sys/fs/cgroup'
        ])

        super(OpenSwitchNode, self).__init__(
            identifier, image=image, command=command, binds=binds, **kwargs
        )

        # Add vtysh shell and make it default
        key, shell = self._shells.popitem()
        self._shells['vtysh'] = DockerShell(self.identifier, 'vtysh', '.*#')
        self._shells[key] = shell

    def notify_post_build(self):
        super(OpenSwitchNode, self).notify_post_build()

        cmd_tpl = """\
            ip link set {iface} netns swns
            ip netns exec swns ip link set {iface} name {port_number}\
        """

        for port_spec in self._ports.values():
            netns, rename = cmd_tpl.format(**port_spec).splitlines()

            # Set interfaces in swns namespace
            self.send_command(netns.lstrip(), shell='bash')

            # FIXME: Remove this when vtysh is fixed
            # Rename interface to make vtysh work
            # Named interfaces are ignored
            if port_spec['port_number'] is not None:
                self.send_command(rename.lstrip(), shell='bash')


__all__ = ['OpenSwitchNode']
