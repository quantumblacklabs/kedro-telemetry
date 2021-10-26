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
# pylint: disable=protected-access

"""Testing module for CLI tools"""
import shutil
import tempfile
from collections import namedtuple
from pathlib import Path

import pytest
from kedro import __version__ as kedro_version
from kedro.framework.cli.cli import KedroCLI, cli
from kedro.framework.startup import ProjectMetadata

from kedro_telemetry.masking import (
    _get_vocabulary,
    _recursive_items,
    get_cli_structure,
    mask_kedro_cli,
)

REPO_NAME = "cli_tools_dummy_project"
PACKAGE_NAME = "cli_tools_dummy_package"
DEFAULT_KEDRO_COMMANDS = [
    "activate-nbstripout",
    "build-docs",
    "build-reqs",
    "catalog",
    "install",
    "ipython",
    "jupyter",
    "lint",
    "new",
    "package",
    "pipeline",
    "registry",
    "run",
    "starter",
    "test",
]


@pytest.fixture(scope="function")
def fake_root_dir():
    # using tempfile as tmp_path fixture doesn't support module scope
    tmpdir = tempfile.mkdtemp()
    try:
        yield Path(tmpdir).resolve()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture(scope="function")
def fake_metadata(fake_root_dir):
    metadata = ProjectMetadata(
        fake_root_dir / REPO_NAME / "pyproject.toml",
        PACKAGE_NAME,
        "CLI Tools Testing Project",
        fake_root_dir / REPO_NAME,
        kedro_version,
        fake_root_dir / REPO_NAME / "src",
    )
    return metadata


class TestCLIMasking:
    def test_get_cli_structure(self, mocker, fake_metadata):
        # This test is a replica of `kedro.tests.tools.test_cli.py` tests
        # This duplication is to maintain backwards compatibility
        Module = namedtuple("Module", ["cli"])
        mocker.patch(
            "kedro.framework.cli.cli.importlib.import_module",
            return_value=Module(cli=cli),
        )
        mocker.patch(
            "kedro.framework.cli.cli._is_project", return_value=True,
        )
        mocker.patch(
            "kedro.framework.cli.cli.bootstrap_project", return_value=fake_metadata,
        )
        kedro_cli = KedroCLI(fake_metadata.project_path)
        raw_cli_structure = get_cli_structure(kedro_cli, get_help=False)
        help_cli_structure = get_cli_structure(kedro_cli, get_help=True)

        # raw CLI structure tests
        assert isinstance(raw_cli_structure, dict)
        assert isinstance(raw_cli_structure["kedro"], dict)

        for k, v in raw_cli_structure["kedro"].items():
            assert isinstance(k, str)
            assert isinstance(v, dict)

        assert sorted(list(raw_cli_structure["kedro"])) == sorted(
            DEFAULT_KEDRO_COMMANDS
        )

        # get_help CLI structure tests
        assert isinstance(help_cli_structure, dict)
        assert isinstance(help_cli_structure["kedro"], dict)

        for k, v in help_cli_structure["kedro"].items():
            assert isinstance(k, str)
            if isinstance(v, dict):
                for sub_key in v:
                    assert isinstance(help_cli_structure["kedro"][k][sub_key], str)
                    assert help_cli_structure["kedro"][k][sub_key].startswith(
                        "Usage:  [OPTIONS]"
                    )
            elif isinstance(v, str):
                assert v.startswith("Usage:  [OPTIONS]")

        assert sorted(list(help_cli_structure["kedro"])) == sorted(
            DEFAULT_KEDRO_COMMANDS
        )

    @pytest.mark.parametrize(
        "input_dict, expected_output_count",
        [
            ({}, 0),
            ({"a": "foo"}, 1),
            ({"a": {"b": "bar"}, "c": {"baz"}}, 3),
            (
                {
                    "a": {"b": "bar"},
                    "c": None,
                    "d": {"e": "fizz"},
                    "f": {"g": {"h": "buzz"}},
                },
                8,
            ),
        ],
    )
    def test_recursive_items(self, input_dict, expected_output_count):
        assert expected_output_count == sum(
            1 for _ in _recursive_items(dictionary=input_dict)
        )

    def test_recursive_items_empty(self):
        assert len(list(_recursive_items({}))) == 0

    @pytest.mark.parametrize(
        "input_dict, expected_tuple",
        [
            (
                {
                    "a": {"b": "bar"},
                    "c": None,
                    "d": {"e": "fizz"},
                    "f": {"g": {"h": "buzz"}},
                },
                ("h", "buzz"),
            ),
            ({"a": {},}, ("a", None)),
        ],
    )
    def test_recursive_items_last_leaf(self, input_dict, expected_tuple):
        assert list(_recursive_items(input_dict))[-1] == expected_tuple

    def test_get_vocabulary_empty(self):
        assert _get_vocabulary({}) == {"-h", "--version"}

    @pytest.mark.parametrize(
        "input_cli_structure, input_command_args, expected_masked_args",
        [
            ({}, [], []),
            (
                {"kedro": {"command_a": None, "command_b": None}},
                ["command_a"],
                ["command_a"],
            ),
            (
                {
                    "kedro": {
                        "command_a": {"--param1": None, "--param2": None},
                        "command_b": None,
                    }
                },
                ["command_a", "--param1=foo"],
                ["command_a", "--param1", "*****"],
            ),
            (
                {
                    "kedro": {
                        "command_a": {"--param1": None, "--param2": None},
                        "command_b": None,
                    }
                },
                ["command_a", "--param1= foo"],
                ["command_a", "--param1", "*****"],
            ),
            (
                {
                    "kedro": {
                        "command_a": {"--param": None, "-p": None},
                        "command_b": None,
                    }
                },
                ["command_a", "-p", "bar"],
                ["command_a", "-p", "*****"],
            ),
            (
                {
                    "kedro": {
                        "command_a": {"--param": None, "-p": None},
                        "command_b": None,
                    }
                },
                ["command_a", "-xyz", "bar"],
                ["command_a", "*****", "*****"],
            ),
            (
                {
                    "kedro": {
                        "command_a": {"--param": None, "-p": None},
                        "command_b": None,
                    }
                },
                ["none", "of", "this", "should", "be", "seen", "except", "command_a"],
                [
                    "*****",
                    "*****",
                    "*****",
                    "*****",
                    "*****",
                    "*****",
                    "*****",
                    "command_a",
                ],
            ),
        ],
    )
    def test_mask_kedro_cli(
        self, input_cli_structure, input_command_args, expected_masked_args
    ):
        assert expected_masked_args == mask_kedro_cli(
            cli_struct=input_cli_structure, command_args=input_command_args
        )
