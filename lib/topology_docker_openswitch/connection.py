# -*- coding: utf-8 -*-

"""
OpenSwitch node module
"""

from __future__ import unicode_literals, absolute_import
from __future__ import print_function, division

from topology_docker.connection import DockerSSHConnection
from topology_docker_openswitch.shell import (
    BASH_FORCED_PROMPT, BASH_START_SHELL_PROMPT,
    VTYSH_STANDARD_PROMPT
)


class OpenswitchSSHConnection(DockerSSHConnection):
    """
    Telnet connection class

    NOTE: this is temporary to facilitate testing of connections, ultimately
    we will need update the shells to operate in the mode where we log strait
    into vtysh and use start-shell to go to bash. for this test we will call
    start shell as part of the login so we can reuse the existing shell code.
    This will only function for users with privileges to start-shell
    """

    def __init__(self, identifier, parent_node, *args, **kwargs):
        super(OpenswitchSSHConnection, self).__init__(
            identifier, parent_node, initial_prompt=VTYSH_STANDARD_PROMPT,
            *args, **kwargs
        )

    def login(self):
        """
        See :meth:`CommonConnection.login` for more information.
        """
        super(OpenswitchSSHConnection, self).login()

        spawn = self._spawn

        spawn.sendline('')
        spawn.expect(self._initial_prompt)
        spawn.sendline('start-shell')
        spawn.expect(BASH_START_SHELL_PROMPT)
        spawn.sendline('export PS1={}'.format(BASH_FORCED_PROMPT))
        spawn.expect(BASH_FORCED_PROMPT)
        spawn.sendline('stty -echo')


__all__ = [
    'OpenswitchSSHConnection'
]
