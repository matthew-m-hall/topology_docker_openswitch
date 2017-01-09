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

from logging import warning
from re import match, search

from pexpect import EOF

from topology.platforms.shell import PExpectBashShell
from topology_docker.shell import DockerShell, DockerBashShell


_VTYSH_PROMPT_TPL = r'(\r\n)?{}(\([-\w\s]+\))?# '
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
    Openswitch Telnet-connected vsctl shell.
    """

    def __init__(self):
        super(OpenSwitchBashShell, self).__init__(
            initial_prompt='(^|\n).*[#$] '
        )

    def _exit(self):
        """
        Attempt a clean exit from the shell.
        """
        try:
            self.send_command('exit', matches=[EOF])
        except Exception as error:
            warning(
                'Exiting the shell failed with this error: {}'.format(
                    str(error)
                )
            )


class OpenSwitchVsctlShell(DockerBashShell):
    """
    Openswitch Telnet-connected vsctl shell.
    """

    def __init__(self):
        super(OpenSwitchVsctlShell, self).__init__(
            initial_prompt='(^|\n).*[#$] ',
            prefix='ovs-vsctl ', timeout=60
        )


class OpenSwitchBashSwnsShell(DockerBashShell):
    """
    Openswitch Telnet-connected ``bash`` ``swns`` shell.

    This shell spawns a ``bash`` shell inside the ``swns`` network namespace.
    """

    def __init__(self):
        super(OpenSwitchBashSwnsShell, self).__init__(
            initial_prompt='(^|\n).*[#$] '
        )

    def enter(self):
        """
        see :meth:`topology.platforms.shell.BaseShell.enter` for more
        information.
        """
        spawn = self._parent_connection._spawn
        spawn.sendline('ip netns exec swns bash')
        spawn.expect(self._prompt)

    def exit(self):
        """
        see :meth:`topology.platforms.shell.BaseShell.exit` for more
        information.
        """
        spawn = self._parent_connection._spawn
        spawn.sendline('exit')
        spawn.expect(self._prompt)

    def _setup_shell(self):
        """
        See :meth:`topology.platforms.shell.BaseShell._setup_shell` for more
        information.
        """

        super(OpenSwitchBashSwnsShell, self)._setup_shell()

        self.enter()


class OpenSwitchVtyshShell(DockerShell):
    """
    OpenSwitch ``vtysh`` shell

    This shell handles the particularities of the ``vtysh`` shell of an
    OpenSwitch node. It is actually a shell that connects first to ``bash`` and
    from the ``bash`` shell it then opens a ``vtysh`` shell.

    The actual process that this shell follows depends on the image of the
    OpenSwitch node. Newer images support the ``vtysh`` ``set prompt`` command,
    older images do not. This command allows the user to change the vtysh
    prompt to any value without other side effects (like the hostname command
    has).

    #. A connection to the ``bash`` shell of the node is done.
    #. The ``bash`` prompt is set to ``@~~==::BASH_PROMPT::==~~@``.
    #. A ``vtysh`` shell is opened with ``stdbuf -oL vtysh``.
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
            '(^|\n).*[#$] ', try_filter_echo=False
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

        spawn.sendline('exit')
        spawn.expect(BASH_FORCED_PROMPT)

        # This is done because vtysh shells for older images enable the bash
        # shell echo.
        spawn.sendline('stty -echo')
        spawn.expect(BASH_FORCED_PROMPT)

    def _setup_shell(self, connection=None):
        """
        Get the shell ready to handle ``vtysh`` particularities.

        These particularities are the handling of segmentation fault errors
        and forced or standard ``vtysh`` prompts.

        See :meth:`PExpectShell._setup_shell` for more information.
        """

        spawn = self._parent_connection._spawn

        # The bash prompt is set to a forced value for vtysh shells that
        # support prompt setting and for the ones that do not.
        spawn.sendline('export PS1={}'.format(BASH_FORCED_PROMPT))
        spawn.expect(BASH_FORCED_PROMPT)

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
            # When a segmentation fault error happens, the message
            # "Segmentation fault" shows up in the terminal and then and EOF
            # follows, making the vtysh shell to close ending up in the bash
            # shell that opened it.

            # This starts the vtysh shell in a mode that forces the shell to
            # always return the produced output, even if an EOF exception
            # follows after it. This is done to handle the segmentation fault
            # errors.
            spawn.sendline('stdbuf -oL vtysh')
            spawn.expect(VTYSH_STANDARD_PROMPT)

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

        def join_prompt(prompt):
            return '{}|{}'.format(BASH_FORCED_PROMPT, prompt)

        if determine_set_prompt(spawn):
            # From now on the shell _prompt attribute is set to the defined
            # vtysh forced prompt.
            self._prompt = join_prompt(VTYSH_FORCED_PROMPT)

        else:
            # If the image does not support "set prompt", then enable the
            # filtering of echo by setting the corresponding attribute to True.
            # WARNING: Using a private attribute here.
            self._try_filter_echo = True

            spawn.sendline('exit')
            spawn.expect(BASH_FORCED_PROMPT)

            # If an older OpenSwitch image is being used here, is necessary to
            # open the vtysh shell with echo enabled. Since a previous usage of
            # the bash shell would have disabled the echo, it is enabled here.
            spawn.sendline('stty sane')
            spawn.expect(BASH_FORCED_PROMPT)

            determine_set_prompt(spawn)

            # From now on the shell _prompt attribute is set to the defined
            # vtysh standard prompt.
            self._prompt = join_prompt(VTYSH_STANDARD_PROMPT)

    def send_command(
        self, command, matches=None, newline=True, timeout=None,
        connection=None, silent=False
    ):
        match_index = super(OpenSwitchVtyshShell, self).send_command(
            command, matches=matches, newline=newline, timeout=timeout,
            silent=silent
        )

        spawn = self._parent_connection._spawn

        # To find out if a segmentation fault error was produced, a search for
        # the "Segmentation fault" string in the output of the command is done.
        segmentation_fault = search(
            r'Segmentation fault', self.get_response(silent=True)
        )

        # The other necessary condition to detect a segmentation fault error is
        # to detect a forced bash prompt being matched.
        forced_bash_prompt = match(
            BASH_FORCED_PROMPT, spawn.after.decode(
                encoding=self._encoding, errors=self._errors
            )
        )

        # This exception is raised to provide a meaningful error to the user.
        if segmentation_fault is not None and forced_bash_prompt is not None:
            raise Exception(
                'Segmentation fault received when executing "{}".'.format(
                    self._last_command
                )
            )

        return match_index

    def _exit(self):
        """
        Attempt a clean exit from the shell.

        This is necessary to enable gathering of coverage information.
        """
        try:
            self.send_command('end', silent=True)
            self.send_command(
                'exit', matches=[EOF, BASH_FORCED_PROMPT],
                silent=True
            )
        except Exception as error:
            warning(
                'Exiting the shell failed with this error: {}'.format(
                    str(error)
                )
            )


__all__ = ['OpenSwitchVtyshShell']
