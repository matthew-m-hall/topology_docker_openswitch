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
OpenSwitch shell module
"""

from __future__ import unicode_literals, absolute_import
from __future__ import print_function, division

from topology.platforms.shell import PExpectBashShell
from topology_docker.shell import DockerShell, DockerBashShell


_VTYSH_PROMPT_TPL = r'(\r\n)?{}(\([-\w\s]+\))?[#>] '
_VTYSH_FORCED = 'X@~~==::VTYSH_PROMPT::==~~@X'
# This is a regular expression that matches with values that may be found in
# unset vtysh prompts:
_VTYSH_STANDARD = '[-\w]+'

VTYSH_FORCED_PROMPT = _VTYSH_PROMPT_TPL.format(_VTYSH_FORCED)
VTYSH_STANDARD_PROMPT = _VTYSH_PROMPT_TPL.format(_VTYSH_STANDARD)

BASH_FORCED_PROMPT = PExpectBashShell.FORCED_PROMPT
# if the bash shell is reached through the vtysh cmd 'start-shell', this
# regular expression will match the defalut prompt
BASH_START_SHELL_PROMPT = r'(\r\n)?[\w\W]+\$ '


class OpenSwitchBashShell(DockerBashShell):
    """
    Openswitch Telnet-connected bash shell.
    """

    def __init__(self, **kwargs):
        super(OpenSwitchBashShell, self).__init__(
            BASH_FORCED_PROMPT, try_filter_echo=False,
            **kwargs
        )

    def enter(self):
        """
        see :meth:`topology.platforms.shell.BaseShell.enter` for more
        information.
        """
        spawn = self._parent_connection._spawn
        spawn.sendline('start-shell')
        spawn.expect(BASH_START_SHELL_PROMPT)

        spawn.sendline('export PS1={}'.format(BASH_FORCED_PROMPT))
        spawn.expect(self._prompt)

        # This is done because vtysh shells for older images enable the bash
        # shell echo.
        spawn.sendline('stty -echo')
        spawn.expect(self._prompt)

    def exit(self):
        """
        see :meth:`topology.platforms.shell.BaseShell.exit` for more
        information.
        """
        spawn = self._parent_connection._spawn
        spawn.sendline('exit')
        spawn.expect(VTYSH_FORCED_PROMPT)

    def _setup_shell(self):
        """
        See :meth:`topology.platforms.shell.BaseShell._setup_shell` for more
        information.
        """

        spawn = self._parent_connection._spawn
        spawn.sendline('start-shell')
        spawn.expect(BASH_START_SHELL_PROMPT)

        super(OpenSwitchBashSwnsShell, self)._setup_shell()


class OpenSwitchVsctlShell(OpenSwitchBashShell):
    """
    Openswitch Telnet-connected vsctl shell.
    """

    def __init__(self):
        super(OpenSwitchVsctlShell, self).__init__(
            prefix='ovs-vsctl ', timeout=60
        )


class OpenSwitchBashSwnsShell(OpenSwitchBashShell):
    """
    Openswitch Telnet-connected ``bash`` ``swns`` shell.

    This shell spawns a ``bash`` shell inside the ``swns`` network namespace.
    """

    def __init__(self, **kwargs):
        self._start_command = 'sudo ip netns exec swns bash'

        super(OpenSwitchBashShell, self).__init__(**kwargs)

    def enter(self):
        """
        see :meth:`topology.platforms.shell.BaseShell.enter` for more
        information.
        """
        super(OpenSwitchBashSwnsShell, self).enter()

        spawn = self._parent_connection._spawn
        spawn.sendline(self._start_command)
        spawn.expect(self._prompt)

    def exit(self):
        """
        see :meth:`topology.platforms.shell.BaseShell.exit` for more
        information.
        """
        spawn = self._parent_connection._spawn
        spawn.sendline('exit')
        spawn.expect(self._prompt)

        super(OpenSwitchBashSwnsShell, self).exit()

    def _setup_shell(self):
        """
        See :meth:`topology.platforms.shell.BaseShell._setup_shell` for more
        information.
        """
        super(OpenSwitchBashSwnsShell, self)._setup_shell()

        spawn = self._parent_connection._spawn
        spawn.sendline(self._start_command)
        spawn.expect(self._prompt)


class OpenSwitchVtyshShell(DockerShell):
    """
    OpenSwitch ``vtysh`` shell

    This shell handles the particularities of the ``vtysh`` shell of an
    OpenSwitch node.

    The actual process that this shell follows depends on the image of the
    OpenSwitch node. Newer images support the ``vtysh`` ``set prompt`` command,
    older images do not. This command allows the user to change the vtysh
    prompt to any value without other side effects (like the hostname command
    has).

    #. The ``vtysh`` ``set prompt X@~~==::VTYSH_PROMPT::==~~@X`` command is
       executed to set the ``vtysh`` forced prompt.

    If the next prompt received matches the ``vtysh`` forced prompt, this
    process is followed:

    #. The ``vtysh`` shell is exited back to the ``bash`` shell by sending
       ``exit``.
    #. The echo of the ``bash`` shell is disabled with ``stty -echo``. This
       will also disable the echo of the ``vtysh`` shell that will be started
       from the ``bash`` shell.
    #. A ``vtysh`` shell will be started with ``stdbuf -oL vtysh``.
    #. The ``vtysh`` ``set prompt X@~~==::VTYSH_PROMPT::==~~@X`` command is
       executed.
    #. The shell prompt is set to the forced ``vtysh`` prompt.
    #. In this case, the shell will not try to remove the echo of the ``vtysh``
       commands because they should not appear since the echo is disabled.

    If the next prompt received does not match the ``vtysh`` forced prompt,
    this process is followed:

    #. The shell is configured to try to remove the echo of the ``vtysh``
       commands by looking for them in the command output.
    #. The shell prompt is set to the standard ``vtysh`` prompt.

    Once the container is to be destroyed in the normal clean up of nodes, the
    ``vtysh`` shell is exited to the ``bash`` one by sending the ``end``
    command followed by the ``exit`` command.
    """

    def __init__(self):
        # The parameter try_filter_echo is disabled by default here to handle
        # images that support the vtysh "set prompt" command and will have its
        # echo disabled since it extends from DockeBashShell. For other
        # situations where this is not supported, the self._try_filter_echo
        # attribute is disabled afterwards by altering it directly.
        # The prompt value passed here is the one that will match with an
        # OpenSwitch bash shell initial prompt.
        super(OpenSwitchVtyshShell, self).__init__(
            VTYSH_FORCED_PROMPT, try_filter_echo=True
        )

    def enter(self):
        """
        see :meth:`topology.platforms.shell.BaseShell.enter` for more
        information.
        """
        self._handle_prompt()

    def exit(self):
        """
        Exit this shell and go into a bash shell.

        see :meth:`topology.platforms.shell.BaseShell.exit` for more
        information.
        """

        spawn = self._parent_connection._spawn

        spawn.sendline('end')
        # This is done to handle calls to hostname that change this prompt.
        spawn.expect([self._prompt, '^.*# '])

    def _setup_shell(self, connection=None):
        """
        Get the shell ready to handle ``vtysh`` particularities.

        These particularities are the handling of segmentation fault errors
        and forced or standard ``vtysh`` prompts.

        See :meth:`PExpectShell._setup_shell` for more information.
        """

        self.enter()

    def _handle_prompt(self):
        """
        Set the correct vtysh prompt.

        Older and newer OpenSwitch images use different vtysh prompts, this
        sets the rigth ones depending on the image.
        """
        spawn = self._parent_connection._spawn

        def determine_set_prompt(spawn):
            """
            This method determines if the vtysh command set prompt exists.

            This method starts wit a call to sendline and finishes with a call
            to expect.

            :rtype: bool
            :return: True if vtysh supports the ``set prompt`` command, False
             otherwise.
            """

            # The newer images of OpenSwitch include this command that changes
            # the prompt of the shell to an unique value. This is done to
            # perform a safe matching that will match only with this value in
            # each expect.
            spawn.sendline('set prompt {}'.format(_VTYSH_FORCED))

            # Since it is not possible to know beforehand if the image loaded
            # in the node includes the "set prompt" command, an attempt to
            # match any of the following prompts is done. If the command does
            # not exist, the shell will return an standard prompt after showing
            # an error message.
            index = spawn.expect(
                [VTYSH_STANDARD_PROMPT, VTYSH_FORCED_PROMPT]
            )

            return bool(index)

        if determine_set_prompt(spawn):
            # From now on the shell _prompt attribute is set to the defined
            # vtysh forced prompt.
            self._prompt = VTYSH_FORCED_PROMPT

        else:
            # If the image does not support "set prompt", then enable the
            # filtering of echo by setting the corresponding attribute to True.
            # WARNING: Using a private attribute here.
            self._try_filter_echo = True

            # only admins have access to the shell,
            # so start-shell will not always succeed
            # if it works we get the bash prompt and set it up
            # if not we will be at the vtysh prompt
            spawn.sendline('start-shell')
            index = spawn.expect(
                [VTYSH_STANDARD_PROMPT, BASH_START_SHELL_PROMPT]
            )

            if bool(index):
                # If an older OpenSwitch image is being used here, is
                # necessary to open the vtysh shell with echo enabled. Since a
                # previous usage of the bash shell would have disabled the
                # echo, it is enabled here.
                spawn.sendline('stty sane')
                spawn.expect(BASH_START_SHELL_PROMPT)

                spawn.sendline('exit')
                spawn.expect(VTYSH_STANDARD_PROMPT)

            # From now on the shell _prompt attribute is set to the defined
            # vtysh standard prompt.
            self._prompt = VTYSH_STANDARD_PROMPT


__all__ = ['OpenSwitchVtyshShell']
