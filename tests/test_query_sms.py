import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "query_sms.py"


def run_cli(*args: str, db: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(db), *args],
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
        env=env,
    )


class DatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "app.db"
        now_ms = int(time.time() * 1000)
        con = sqlite3.connect(self.db)
        con.execute(
            "CREATE TABLE text_messages ("
            "id TEXT, \"from\" TEXT, \"to\" TEXT, content TEXT, type TEXT, "
            "status TEXT, created_at INTEGER, updated_at INTEGER)"
        )
        con.execute(
            "CREATE TABLE properties (id TEXT, name TEXT, value TEXT, created_at INTEGER, updated_at INTEGER)"
        )
        con.execute(
            "INSERT INTO properties VALUES ('1', 'secret', 'do-not-read', 0, 0)"
        )
        rows = [
            ("zj", "10650001", "【浙里办】本次操作所需的验证码为：222222。", now_ms - 60 * 1000),
            ("nat", "10650002", "【国家医疗保障局】验证码333333，5分钟内有效。", now_ms - 2 * 60 * 1000),
            ("hn", "10650003", "【湖南省医疗保障局】短信验证码为：444444。", now_ms - 3 * 60 * 1000),
            ("old", "10650004", "【天津市医疗保障局】短信验证码为：111111。", now_ms - 30 * 60 * 1000),
        ]
        con.executemany(
            'INSERT INTO text_messages (id, "from", content, type, status, created_at, updated_at) '
            "VALUES (?, ?, ?, 'incoming', 'received', ?, ?)",
            [(item[0], item[1], item[2], item[3], item[3]) for item in rows],
        )
        con.execute(
            'INSERT INTO text_messages (id, "from", content, type, status, created_at, updated_at) '
            "VALUES ('out', 'me', '发出的验证码555555', 'outgoing', 'sent', ?, ?)",
            (now_ms, now_ms),
        )
        con.commit()
        con.close()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_returns_text_for_the_caller_to_judge(self) -> None:
        result = run_cli("--recent", "10", db=self.db)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        contents = [item["content"] for item in payload["messages"]]
        self.assertEqual(len(contents), 4)
        self.assertTrue(any("浙里办" in item for item in contents))
        self.assertTrue(any("国家医疗保障局" in item for item in contents))
        self.assertTrue(any("湖南省医疗保障局" in item for item in contents))
        self.assertNotIn("555555", result.stdout)
        self.assertNotIn("do-not-read", result.stdout)
        self.assertNotIn("code", payload["messages"][0])

    def test_query_is_only_a_substring_filter(self) -> None:
        result = run_cli("--query", "湖南", db=self.db)
        payload = json.loads(result.stdout)
        self.assertEqual(len(payload["messages"]), 1)
        self.assertIn("444444", payload["messages"][0]["content"])

    def test_within_limits_age(self) -> None:
        result = run_cli("--within", "10", db=self.db)
        contents = [item["content"] for item in json.loads(result.stdout)["messages"]]
        self.assertEqual(len(contents), 3)
        self.assertFalse(any("111111" in item for item in contents))

    def test_redact_hides_codes_but_keeps_context(self) -> None:
        result = run_cli("--query", "浙里办", "--redact", db=self.db)
        self.assertIn("浙里办", result.stdout)
        self.assertNotIn("222222", result.stdout)
        self.assertIn("<6位验证码>", result.stdout)

    def test_status_has_no_message_body(self) -> None:
        result = run_cli("--status", db=self.db)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("222222", result.stdout)
        self.assertEqual(json.loads(result.stdout)["incoming"], 4)

    def test_empty_window(self) -> None:
        result = run_cli("--within", "0.01", "--query", "不存在的平台", db=self.db)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["error"], "not_found")


if __name__ == "__main__":
    unittest.main()
