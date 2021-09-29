# Copyright 2021 QuantumBlack Visual Analytics Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
# OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND
# NONINFRINGEMENT. IN NO EVENT WILL THE LICENSOR OR OTHER CONTRIBUTORS
# BE LIABLE FOR ANY CLAIM, DAMAGES, OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF, OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#
# The QuantumBlack Visual Analytics Limited ("QuantumBlack") name and logo
# (either separately or in combination, "QuantumBlack Trademarks") are
# trademarks of QuantumBlack. The License does not grant you any right or
# license to the QuantumBlack Trademarks. You may not use the QuantumBlack
# Trademarks or any confusingly similar mark as a trademark for your product,
# or use the QuantumBlack Trademarks in any other manner that might cause
# confusion in the marketplace, including but not limited to in advertising,
# on websites, or on software.
#
# See the License for the specific language governing permissions and
# limitations under the License.

"""Kedro Telemetry plugin for collecting Kedro usage data."""

import hashlib
import json
import logging
import os
import socket
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import click
import requests
import yaml
from kedro.framework.cli.hooks import cli_hook_impl
from kedro.framework.startup import ProjectMetadata

from kedro_telemetry import __version__ as telemetry_version

HEAP_APPID_PROD = "2388822444"

HEAP_ENDPOINT = "https://heapanalytics.com/api/track"
HEAP_HEADERS = {"Content-Type": "application/json"}
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"

logger = logging.getLogger(__name__)


class KedroTelemetryCLIHooks:
    """Hook to send CLI command data to Heap"""

    # pylint: disable=too-few-public-methods

    @cli_hook_impl
    def before_command_run(
        self, project_metadata: ProjectMetadata, command_args: List[str]
    ):
        """Hook implementation to send command run data to Heap"""
        # pylint: disable=no-self-use
        masked_command_args = _mask_arguments(command_args)

        main_command = masked_command_args[0] if masked_command_args else "kedro"
        if not project_metadata:  # in package mode
            return

        consent = _check_for_telemetry_consent(project_metadata.project_path)
        if not consent:
            click.secho(
                "Kedro-Telemetry is installed, but you have opted out of "
                "sharing usage analytics so none will be collected.",
                fg="green",
            )
            return

        logger.info("You have opted into product usage analytics.")

        try:
            hashed_computer_name = hashlib.sha512(
                bytes(socket.gethostname(), encoding="utf8")
            )
        except socket.timeout as exc:
            logger.warning(
                "Socket timeout when trying to get the computer name. "
                "No data was sent to Heap. Exception: %s",
                exc,
            )
            return

        properties = _format_user_cli_data(masked_command_args, project_metadata)

        _send_heap_event(
            event_name=f"Command run: {main_command}",
            identity=hashed_computer_name.hexdigest(),
            properties=properties,
        )

        # send generic event too so it's easier in data processing
        generic_properties = deepcopy(properties)
        generic_properties["main_command"] = main_command
        _send_heap_event(
            event_name="CLI command",
            identity=hashed_computer_name.hexdigest(),
            properties=generic_properties,
        )


def _format_user_cli_data(command_args: List[str], project_metadata: ProjectMetadata):
    """Hash username, format CLI command, system and project data to send to Heap."""
    hashed_username = ""
    try:
        hashed_username = hashlib.sha512(bytes(os.getlogin(), encoding="utf8"))
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning(
            "Something went wrong with getting the username to send to Heap. "
            "Exception: %s",
            exc,
        )

    hashed_package_name = hashlib.sha512(
        bytes(project_metadata.package_name, encoding="utf8")
    )
    hashed_project_name = hashlib.sha512(
        bytes(project_metadata.project_name, encoding="utf8")
    )
    project_version = project_metadata.project_version

    return {
        "username": hashed_username.hexdigest() if hashed_username else "anonymous",
        "command": f"kedro {' '.join(command_args)}" if command_args else "kedro",
        "package_name": hashed_package_name.hexdigest(),
        "project_name": hashed_project_name.hexdigest(),
        "project_version": project_version,
        "telemetry_version": telemetry_version,
        "python_version": sys.version,
        "os": sys.platform,
    }


def _get_heap_app_id() -> str:
    """
    Get the Heap App ID to send the data to.
    This will be the development ID if it's set as an
    environment variable, otherwise it will be the production ID.
    """
    return os.environ.get("HEAP_APPID_DEV", HEAP_APPID_PROD)


def _send_heap_event(
    event_name: str, identity: str, properties: Dict[str, Any] = None
) -> None:
    data = {
        "app_id": _get_heap_app_id(),
        "identity": identity,
        "event": event_name,
        "timestamp": datetime.now().strftime(TIMESTAMP_FORMAT),
        "properties": properties or {},
    }

    resp = requests.post(url=HEAP_ENDPOINT, headers=HEAP_HEADERS, data=json.dumps(data))
    if resp.status_code != 200:
        logger.warning(
            "Failed to send data to Heap. Response code returned: %s, Response reason: %s",
            resp.status_code,
            resp.reason,
        )


def _check_for_telemetry_consent(project_path: Path) -> bool:
    telemetry_file_path = project_path / ".telemetry"
    if not telemetry_file_path.exists():
        return _confirm_consent(telemetry_file_path)
    with open(telemetry_file_path, encoding="utf-8") as telemetry_file:
        telemetry = yaml.safe_load(telemetry_file)
        if _is_valid_syntax(telemetry):
            return telemetry["consent"]
        return _confirm_consent(telemetry_file_path)


def _is_valid_syntax(telemetry: Any) -> bool:
    return isinstance(telemetry, dict) and isinstance(
        telemetry.get("consent", None), bool
    )


def _confirm_consent(telemetry_file_path: Path) -> bool:
    with telemetry_file_path.open("w") as telemetry_file:
        confirm_msg = (
            "As an open-source project, we collect usage analytics. \n"
            "We cannot see nor store information contained in "
            "a Kedro project. \nYou can find out more by reading our "
            "privacy notice: \n"
            "https://github.com/quantumblacklabs/kedro-telemetry#privacy-notice \n"
            "Do you opt into usage analytics? "
        )
        if click.confirm(confirm_msg):
            yaml.dump({"consent": True}, telemetry_file)
            click.secho("You have opted into product usage analytics.", fg="green")
            return True
        yaml.dump({"consent": False}, telemetry_file)
        return False


def _mask_arguments(command_args: List[str]) -> List[str]:
    """Masks any arguments passed, such as pipeline and node names.
    Ensures these are masked client-side"""
    _eq = "="
    _mask = "*****"
    masked_commands = []
    command_args_iterable = iter(command_args)

    for arg in command_args_iterable:
        if arg.startswith("-"):
            # this if-else groups together arguments with "=" operator
            # as well as those separated by whitespace
            if _eq in arg:
                masked_commands.append(arg.split(_eq, 1)[0])
                masked_commands.append(_mask)
            else:
                masked_commands.append(arg)
                next_arg = next(command_args_iterable, None)
                if next_arg:
                    masked_commands.append(_mask)
        else:
            masked_commands.append(arg)

    return list(filter(None, masked_commands))


cli_hooks = KedroTelemetryCLIHooks()
