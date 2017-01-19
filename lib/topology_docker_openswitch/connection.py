# -*- coding: utf-8 -*-

"""
OpenSwitch node module
"""

from __future__ import unicode_literals, absolute_import
from __future__ import print_function, division

from time import sleep

from topology_docker.connection import (
    DockerConnection, DockerSSHConnection
)
from topology_docker_openswitch.shell import (
    BASH_FORCED_PROMPT, BASH_START_SHELL_PROMPT,
    VTYSH_STANDARD_PROMPT
)


class OpenswitchDockerConnection(DockerConnection):
    """
    Docker ``exec`` connection for the Topology docker.

    This class implements a ``_get_connect_command()`` method that allows to
    interact with a shell through a ``docker exec`` interactive command, and
    extends the constructor to request for container related parameters.

    :param str container: Container unique identifier.
    :param str command: Command to be executed with the ``docker exec`` that
     will launch an interactive session.
    """

    def __init__(self, identifier, parent_node, user='admin',
                 password='admin', **kwargs):
        self._container_id = parent_node.container_id
        super(DockerConnection, self).__init__(
            identifier, parent_node, user=user, password=password,
            initial_prompt=VTYSH_STANDARD_PROMPT, **kwargs)

    def _get_connect_command(self):
        return 'docker exec -i -t {} login'.format(
            self._container_id
        )

    def login(self):
        """
        See :meth:`CommonConnection.login` for more information.
        """
        spawn = self._spawn

        spawn.expect(r'(?<!Last )login:')

        spawn.sendline(self._user)
        # This is necessary to avoid wrong matching due to OpenSwitch slow
        # output return.
        sleep(0.5)

        spawn.expect(r'Password:')
        spawn.sendline(self._password)

        spawn.expect(self._initial_prompt)

        # only admins have access to the shell,
        # so start-shell will not always succeed
        # if it works we get the bash prompt and set it up
        # if not we will be at the vtysh prompt
        spawn.sendline('start-shell')
        index = spawn.expect([self._initial_prompt, BASH_START_SHELL_PROMPT])

        if bool(index):
            spawn.sendline('export PS1={}'.format(BASH_FORCED_PROMPT))
            spawn.expect(BASH_FORCED_PROMPT)
            spawn.sendline('stty -echo')
            spawn.expect(BASH_FORCED_PROMPT)
            spawn.sendline('exit')
            spawn.expect(self._initial_prompt)


class OpenswitchSSHConnection(DockerSSHConnection):
    """
    SSH connection class
    """

    def __init__(self, identifier, parent_node, user='admin',
                 password='admin', *args, **kwargs):
        super(OpenswitchSSHConnection, self).__init__(
            identifier, parent_node, initial_prompt=VTYSH_STANDARD_PROMPT,
            user=user, password=password, *args, **kwargs
        )

    def login(self):
        """
        See :meth:`CommonConnection.login` for more information.
        """
        super(OpenswitchSSHConnection, self).login()

        spawn = self._spawn

        spawn.sendline('')
        spawn.expect(self._initial_prompt)

        # only admins have access to the shell,
        # so start-shell will not always succeed
        # if it works we get the bash prompt and set it up
        # if not we will be at the vtysh prompt
        spawn.sendline('start-shell')
        index = spawn.expect([self._initial_prompt, BASH_START_SHELL_PROMPT])

        if bool(index):
            spawn.sendline('export PS1={}'.format(BASH_FORCED_PROMPT))
            spawn.expect(BASH_FORCED_PROMPT)
            spawn.sendline('stty -echo')
            spawn.expect(BASH_FORCED_PROMPT)
            spawn.sendline('exit')
            spawn.expect(self._initial_prompt)


__all__ = [
    'OpenswitchSSHConnection'
]
