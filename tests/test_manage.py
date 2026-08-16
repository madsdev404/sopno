"""
tests/test_manage.py
━━━━━━━━━━━━━━━━━━━━
Automated unit tests for the process / service / log / cron management tools.
"""

import unittest
from unittest.mock import patch, MagicMock

from sopno.tools.builtins import manage
from sopno.tools.builtins.manage import (
    kill_process,
    list_processes,
    manage_cron,
    manage_service,
    read_logs,
)

_PS_OUTPUT = """USER     PID  %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND
mads     100  12.5  1.0 123456 78901 ?        S    10:00   0:05 /usr/bin/python3 app.py
mads     101   5.0  0.5  11111 22222 ?        S    10:01   0:01 firefox
root     102   0.0  0.1   2345  1234 ?        Ss   10:02   0:00 /usr/lib/systemd/systemd --user
"""


def _ok(stdout: str = "", exit_code: int = 0) -> dict:
    return {"stdout": stdout, "exit_code": exit_code, "completed": True, "state": "idle"}


def _blocked(reason: str = "shutdown") -> dict:
    return {"stdout": "", "exit_code": None, "completed": True,
            "state": "idle", "blocked": reason}


def _error(msg: str = "Terminal error: boom") -> dict:
    return {"stdout": "", "exit_code": None, "completed": True,
            "state": "idle", "error": msg}


class TestListProcesses(unittest.TestCase):
    def test_formats_and_filters(self) -> None:
        with patch.object(manage, "_run_command_raw", return_value=_ok(_PS_OUTPUT)):
            out = list_processes("python", limit=5)
        self.assertIn("Running processes:", out)
        self.assertIn("python3 app.py", out)
        self.assertNotIn("firefox", out)

    def test_no_match(self) -> None:
        with patch.object(manage, "_run_command_raw", return_value=_ok(_PS_OUTPUT)):
            out = list_processes("zzznope")
        self.assertEqual(out, "No processes match 'zzznope'.")

    def test_limit_caps_rows(self) -> None:
        with patch.object(manage, "_run_command_raw", return_value=_ok(_PS_OUTPUT)):
            out = list_processes(limit=1)
        self.assertEqual(out.count("\n"), 2)  # header + 1 row

    def test_limit_clamped(self) -> None:
        with patch.object(manage, "_run_command_raw", return_value=_ok(_PS_OUTPUT)):
            out = list_processes(limit=999)
        self.assertEqual(out.count("\n"), 4)  # header + 3 rows

    def test_blocked_propagates(self) -> None:
        with patch.object(manage, "_run_command_raw", return_value=_blocked()):
            self.assertIn("Blocked by safety policy", list_processes())

    def test_error_propagates(self) -> None:
        with patch.object(manage, "_run_command_raw", return_value=_error()):
            self.assertIn("Terminal error", list_processes())


class TestKillProcess(unittest.TestCase):
    def test_kill_by_pid(self) -> None:
        with patch.object(manage, "_run_command_raw", return_value=_ok()) as mock_raw:
            out = kill_process("4321")
        self.assertEqual(out, "Sent SIGTERM to 4321.")
        mock_raw.assert_called_once_with("kill -TERM 4321")

    def test_kill_by_pid_with_signal(self) -> None:
        with patch.object(manage, "_run_command_raw", return_value=_ok()) as mock_raw:
            kill_process("4321", signal="kill")
        mock_raw.assert_called_once_with("kill -KILL 4321")

    def test_kill_by_name(self) -> None:
        with patch.object(manage, "_run_command_raw", return_value=_ok()) as mock_raw:
            out = kill_process("firefox")
        self.assertEqual(out, "Sent SIGTERM to firefox.")
        mock_raw.assert_called_once_with("pkill -TERM -x firefox")

    def test_rejects_kernel_and_init(self) -> None:
        self.assertIn("won't kill", kill_process("1"))
        self.assertIn("won't kill", kill_process("0"))

    def test_rejects_critical_names(self) -> None:
        self.assertIn("won't kill", kill_process("sopno"))
        self.assertIn("won't kill", kill_process("init"))
        self.assertIn("won't kill", kill_process("systemd"))

    def test_rejects_shell_session(self) -> None:
        with patch.object(manage, "_shell_pid", return_value=777):
            self.assertIn("won't kill", kill_process("777"))
            self.assertIn("won't kill", kill_process("bash"))

    def test_rejects_invalid_target(self) -> None:
        self.assertIn("Invalid process name", kill_process("foo;rm -rf /"))
        self.assertIn("Invalid process name", kill_process("-1"))

    def test_rejects_bad_signal(self) -> None:
        self.assertIn("Unsupported signal", kill_process("100", "SEGV"))

    def test_empty_target(self) -> None:
        self.assertIn("Please provide", kill_process(""))

    def test_not_found(self) -> None:
        with patch.object(manage, "_run_command_raw",
                          return_value=_ok(stdout="", exit_code=1)):
            self.assertIn("Could not kill", kill_process("nope"))

    def test_blocked_propagates(self) -> None:
        with patch.object(manage, "_run_command_raw", return_value=_blocked()):
            self.assertIn("Blocked by safety policy", kill_process("firefox"))


class TestManageService(unittest.TestCase):
    def test_start(self) -> None:
        with patch.object(manage, "_run_command_raw", return_value=_ok()) as mock_raw:
            out = manage_service("start", "sopno.service")
        self.assertEqual(out, "Service sopno.service started.")
        mock_raw.assert_called_once_with("systemctl --user start sopno.service")

    def test_status_appends_head(self) -> None:
        with patch.object(manage, "_run_command_raw", return_value=_ok("active (running)")) as mock_raw:
            out = manage_service("status", "sopno")
        self.assertIn("active (running)", out)
        mock_raw.assert_called_once_with(
            "systemctl --user status sopno --no-pager -l | head -n 15"
        )

    def test_invalid_action(self) -> None:
        self.assertIn("Unknown service action", manage_service("explode", "x"))

    def test_invalid_service_name(self) -> None:
        self.assertIn("Invalid service name", manage_service("start", "bad;name"))

    def test_failure(self) -> None:
        with patch.object(manage, "_run_command_raw",
                          return_value=_ok(stdout="Failed to start", exit_code=1)):
            out = manage_service("start", "sopno")
        self.assertIn("Could not start service sopno", out)
        self.assertIn("Failed to start", out)

    def test_blocked_propagates(self) -> None:
        with patch.object(manage, "_run_command_raw", return_value=_blocked()):
            self.assertIn("Blocked by safety policy", manage_service("start", "x"))


class TestReadLogs(unittest.TestCase):
    def test_user_journal(self) -> None:
        with patch.object(manage, "_run_command_raw", return_value=_ok("Aug 16 12:00 line")) as mock_raw:
            out = read_logs("user", lines=10)
        self.assertIn("line", out)
        mock_raw.assert_called_once_with("journalctl --user -n 10 --no-pager -o short")

    def test_system_journal_with_unit(self) -> None:
        with patch.object(manage, "_run_command_raw", return_value=_ok("x")) as mock_raw:
            read_logs("system", unit="ssh.service")
        mock_raw.assert_called_once_with(
            "journalctl --system -u ssh.service -n 30 --no-pager -o short"
        )

    def test_file_tail(self) -> None:
        with patch.object(manage, "_run_command_raw", return_value=_ok("tail line")) as mock_raw:
            out = read_logs("/var/log/syslog", lines=20)
        self.assertIn("tail line", out)
        mock_raw.assert_called_once_with("tail -n 20 /var/log/syslog")

    def test_lines_clamped(self) -> None:
        with patch.object(manage, "_run_command_raw", return_value=_ok("")) as mock_raw:
            read_logs(lines=9999)
        self.assertIn("-n 300", mock_raw.call_args[0][0])

    def test_invalid_source(self) -> None:
        self.assertIn("Unknown log source", read_logs("nowhere"))

    def test_invalid_path(self) -> None:
        self.assertIn("Invalid log path", read_logs("/etc/passwd; echo"))

    def test_invalid_unit(self) -> None:
        self.assertIn("Invalid unit name", read_logs("user", unit="bad;unit"))


class TestManageCron(unittest.TestCase):
    def test_list_empty(self) -> None:
        with patch.object(manage, "_run_command_raw",
                          return_value=_ok(stdout="no crontab for mads")):
            out = manage_cron("list")
        self.assertEqual(out, "No cron jobs for this user.")

    def test_list_shows_jobs(self) -> None:
        crontab = "0 9 * * * echo morning\n# comment\n@daily /usr/bin/backup\n"
        with patch.object(manage, "_run_command_raw", return_value=_ok(crontab)):
            out = manage_cron("list")
        self.assertIn("Cron jobs:", out)
        self.assertIn("echo morning", out)
        self.assertIn("@daily /usr/bin/backup", out)

    def test_add_installs_new_crontab(self) -> None:
        def fake(command, timeout=None):
            if command == "crontab -l":
                return _ok(stdout="0 9 * * * echo old\n")
            assert command.startswith("crontab /tmp/sopno-cron-")
            return _ok()

        with patch.object(manage, "_run_command_raw", side_effect=fake) as mock_raw:
            out = manage_cron("add", "30 18 * * *", "echo backup")
        self.assertIn("Added cron job", out)
        self.assertEqual(mock_raw.call_count, 2)
        install_cmd = mock_raw.call_args_list[1].args[0]
        self.assertTrue(install_cmd.startswith("crontab /tmp/sopno-cron-"))

    def test_add_duplicate(self) -> None:
        with patch.object(manage, "_run_command_raw",
                          return_value=_ok(stdout="0 9 * * * echo morning\n")):
            out = manage_cron("add", "0 9 * * *", "echo morning")
        self.assertIn("already exists", out)

    def test_add_bad_schedule(self) -> None:
        with patch.object(manage, "_run_command_raw", return_value=_ok("")):
            out = manage_cron("add", "tomorrow", "echo hi")
        self.assertIn("Invalid schedule", out)

    def test_add_blocked_command_refused(self) -> None:
        with patch.object(manage, "_run_command_raw", return_value=_ok("")):
            out = manage_cron("add", "0 0 * * *", "rm -rf /")
        self.assertIn("Refusing to schedule a blocked command", out)

    def test_add_missing_args(self) -> None:
        with patch.object(manage, "_run_command_raw", return_value=_ok("")):
            self.assertIn("schedule and a command", manage_cron("add"))

    def test_remove_matching_job(self) -> None:
        crontab = "0 9 * * * echo morning\n30 18 * * * echo backup\n"

        def fake(command, timeout=None):
            if command == "crontab -l":
                return _ok(crontab)
            assert command.startswith("crontab /tmp/sopno-cron-")
            return _ok()

        with patch.object(manage, "_run_command_raw", side_effect=fake):
            out = manage_cron("remove", command="echo backup")
        self.assertIn("Removed 1 cron job", out)

    def test_remove_not_found(self) -> None:
        with patch.object(manage, "_run_command_raw",
                          return_value=_ok(stdout="0 9 * * * echo morning\n")):
            out = manage_cron("remove", command="echo nowhere")
        self.assertIn("was found", out)

    def test_unknown_action(self) -> None:
        self.assertIn("Unknown cron action", manage_cron("explode"))

    def test_blocked_propagates(self) -> None:
        with patch.object(manage, "_run_command_raw", return_value=_blocked()):
            self.assertIn("Blocked by safety policy", manage_cron("list"))


if __name__ == "__main__":
    unittest.main()
