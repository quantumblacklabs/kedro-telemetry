import socket
import sys
from pathlib import Path

import yaml
from kedro import __version__ as kedro_version
from kedro.framework.startup import ProjectMetadata
from pytest import fixture

from kedro_telemetry import __version__ as telemetry_version
from kedro_telemetry.plugin import KedroTelemetryCLIHooks, _check_for_telemetry_consent

REPO_NAME = "dummy_project"
PACKAGE_NAME = "dummy_package"

# pylint: disable=too-few-public-methods


@fixture
def fake_metadata(tmp_path):
    metadata = ProjectMetadata(
        tmp_path / REPO_NAME / "pyproject.toml",
        PACKAGE_NAME,
        "CLI Testing Project",
        tmp_path / REPO_NAME,
        kedro_version,
        tmp_path / REPO_NAME / "src",
    )
    return metadata


class TestKedroTelemetryCLIHooks:
    def test_before_command_run(self, mocker, fake_metadata):
        mocker.patch(
            "kedro_telemetry.plugin._check_for_telemetry_consent", return_value=True
        )
        mocked_anon_id = mocker.patch("hashlib.sha512")
        mocked_anon_id.return_value.hexdigest.return_value = "digested"

        mocked_heap_call = mocker.patch("kedro_telemetry.plugin._send_heap_event")
        telemetry_hook = KedroTelemetryCLIHooks()
        command_args = ["--version"]
        telemetry_hook.before_command_run(fake_metadata, command_args)
        expected_properties = {
            "username": "digested",
            "command": "kedro --version",
            "package_name": "digested",
            "project_name": "digested",
            "project_version": kedro_version,
            "telemetry_version": telemetry_version,
            "python_version": sys.version,
            "os": sys.platform,
        }
        generic_properties = {
            "main_command": "--version",
            **expected_properties,
        }

        expected_calls = [
            mocker.call(
                event_name="Command run: --version",
                identity="digested",
                properties=expected_properties,
            ),
            mocker.call(
                event_name="CLI command",
                identity="digested",
                properties=generic_properties,
            ),
        ]
        assert mocked_heap_call.call_args_list == expected_calls

    def test_before_command_run_empty_args(self, mocker, fake_metadata):
        mocker.patch(
            "kedro_telemetry.plugin._check_for_telemetry_consent", return_value=True
        )
        mocked_anon_id = mocker.patch("hashlib.sha512")
        mocked_anon_id.return_value.hexdigest.return_value = "digested"

        mocked_heap_call = mocker.patch("kedro_telemetry.plugin._send_heap_event")
        telemetry_hook = KedroTelemetryCLIHooks()
        command_args = []
        telemetry_hook.before_command_run(fake_metadata, command_args)
        expected_properties = {
            "username": "digested",
            "command": "kedro",
            "package_name": "digested",
            "project_name": "digested",
            "project_version": kedro_version,
            "telemetry_version": telemetry_version,
            "python_version": sys.version,
            "os": sys.platform,
        }
        generic_properties = {
            "main_command": "kedro",
            **expected_properties,
        }

        expected_calls = [
            mocker.call(
                event_name="Command run: kedro",
                identity="digested",
                properties=expected_properties,
            ),
            mocker.call(
                event_name="CLI command",
                identity="digested",
                properties=generic_properties,
            ),
        ]

        assert mocked_heap_call.call_args_list == expected_calls

    def test_before_command_run_no_consent_given(self, mocker, fake_metadata):
        mocker.patch(
            "kedro_telemetry.plugin._check_for_telemetry_consent", return_value=False
        )

        mocked_heap_call = mocker.patch("kedro_telemetry.plugin._send_heap_event")
        telemetry_hook = KedroTelemetryCLIHooks()
        command_args = ["--version"]
        telemetry_hook.before_command_run(fake_metadata, command_args)

        mocked_heap_call.assert_not_called()

    def test_before_command_run_socket_timeout(self, mocker, fake_metadata):
        mocker.patch(
            "kedro_telemetry.plugin._check_for_telemetry_consent", return_value=True
        )
        telemetry_hook = KedroTelemetryCLIHooks()
        command_args = ["--version"]
        mocker.patch("socket.gethostname", side_effect=socket.timeout)
        mocked_heap_call = mocker.patch("kedro_telemetry.plugin._send_heap_event")

        telemetry_hook.before_command_run(fake_metadata, command_args)

        mocked_heap_call.assert_not_called()

    def test_before_command_run_anonymous(self, mocker, fake_metadata):
        mocker.patch(
            "kedro_telemetry.plugin._check_for_telemetry_consent", return_value=True
        )
        mocked_anon_id = mocker.patch("hashlib.sha512")
        mocked_anon_id.return_value.hexdigest.return_value = "digested"
        mocker.patch("os.getlogin", side_effect=Exception)
        mocked_heap_call = mocker.patch("kedro_telemetry.plugin._send_heap_event")
        telemetry_hook = KedroTelemetryCLIHooks()
        command_args = ["--version"]
        telemetry_hook.before_command_run(fake_metadata, command_args)
        expected_properties = {
            "username": "anonymous",
            "command": "kedro --version",
            "package_name": "digested",
            "project_name": "digested",
            "project_version": kedro_version,
            "telemetry_version": telemetry_version,
            "python_version": sys.version,
            "os": sys.platform,
        }
        generic_properties = {
            "main_command": "--version",
            **expected_properties,
        }

        expected_calls = [
            mocker.call(
                event_name="Command run: --version",
                identity="digested",
                properties=expected_properties,
            ),
            mocker.call(
                event_name="CLI command",
                identity="digested",
                properties=generic_properties,
            ),
        ]
        assert mocked_heap_call.call_args_list == expected_calls

    def test_check_for_telemetry_consent_given(self, mocker, fake_metadata):
        Path(fake_metadata.project_path, "conf").mkdir(parents=True)
        telemetry_file_path = fake_metadata.project_path / ".telemetry"
        with open(telemetry_file_path, "w", encoding="utf-8") as telemetry_file:
            yaml.dump({"consent": True}, telemetry_file)

        mock_create_file = mocker.patch("kedro_telemetry.plugin._confirm_consent")
        mock_create_file.assert_not_called()
        assert _check_for_telemetry_consent(fake_metadata.project_path)

    def test_check_for_telemetry_consent_not_given(self, mocker, fake_metadata):
        Path(fake_metadata.project_path, "conf").mkdir(parents=True)
        telemetry_file_path = fake_metadata.project_path / ".telemetry"
        with open(telemetry_file_path, "w", encoding="utf-8") as telemetry_file:
            yaml.dump({"consent": False}, telemetry_file)

        mock_create_file = mocker.patch("kedro_telemetry.plugin._confirm_consent")
        mock_create_file.assert_not_called()
        assert not _check_for_telemetry_consent(fake_metadata.project_path)

    def test_check_for_telemetry_consent_empty_file(self, mocker, fake_metadata):
        Path(fake_metadata.project_path, "conf").mkdir(parents=True)
        telemetry_file_path = fake_metadata.project_path / ".telemetry"
        mock_create_file = mocker.patch(
            "kedro_telemetry.plugin._confirm_consent", return_value=True
        )

        assert _check_for_telemetry_consent(fake_metadata.project_path)
        mock_create_file.assert_called_once_with(telemetry_file_path)

    def test_check_for_telemetry_no_consent_empty_file(self, mocker, fake_metadata):
        Path(fake_metadata.project_path, "conf").mkdir(parents=True)
        telemetry_file_path = fake_metadata.project_path / ".telemetry"
        mock_create_file = mocker.patch(
            "kedro_telemetry.plugin._confirm_consent", return_value=False
        )

        assert not _check_for_telemetry_consent(fake_metadata.project_path)
        mock_create_file.assert_called_once_with(telemetry_file_path)

    def test_check_for_telemetry_consent_file_no_consent_field(
        self, mocker, fake_metadata
    ):
        Path(fake_metadata.project_path, "conf").mkdir(parents=True)
        telemetry_file_path = fake_metadata.project_path / ".telemetry"
        with open(telemetry_file_path, "w", encoding="utf8") as telemetry_file:
            yaml.dump({"nonsense": "bla"}, telemetry_file)

        mock_create_file = mocker.patch(
            "kedro_telemetry.plugin._confirm_consent", return_value=True
        )

        assert _check_for_telemetry_consent(fake_metadata.project_path)
        mock_create_file.assert_called_once_with(telemetry_file_path)

    def test_check_for_telemetry_consent_file_invalid_yaml(self, mocker, fake_metadata):
        Path(fake_metadata.project_path, "conf").mkdir(parents=True)
        telemetry_file_path = fake_metadata.project_path / ".telemetry"
        telemetry_file_path.write_text("invalid_ yaml")

        mock_create_file = mocker.patch(
            "kedro_telemetry.plugin._confirm_consent", return_value=True
        )

        assert _check_for_telemetry_consent(fake_metadata.project_path)
        mock_create_file.assert_called_once_with(telemetry_file_path)
