"""
YTSage Web UI - offline smoke / regression tests
================================================

Run from the repository root:

    python webui/tests/test_smoke.py          # no pytest needed
    python -m pytest webui/tests -q           # if pytest is installed

These tests touch no network and no real config:
  * password hashing is exercised on throw-away values,
  * the download path / yt-dlp option guards are pure functions,
  * the job-field test is the guard for the bug that broke every download
    (DownloadJob was missing `retries`/`fragment_retries`, so
    build_ytdlp_command raised AttributeError and stalled the whole queue).
"""

import ast
import inspect
import json
import os
import sys
from pathlib import Path

# Allow `python webui/tests/test_smoke.py` from the repo root.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from webui import system_service  # noqa: E402
from webui.auth import (  # noqa: E402
    _hash_password,
    _legacy_hash,
    create_token,
    verify_against_hash,
    verify_token,
)
from webui.command_service import command_service  # noqa: E402
from webui.download_manager import DownloadJob, build_ytdlp_command  # noqa: E402

_PASSED = []
_FAILED = []


def check(name, condition):
    (_PASSED if condition else _FAILED).append(name)
    print(f"  {'ok  ' if condition else 'FAIL'} {name}")


# ---------------------------------------------------------------------------
# 1. Job fields vs. command builder (the regression that stalled all downloads)
# ---------------------------------------------------------------------------

def test_job_fields_cover_command_builder():
    """Every `job.<attr>` used by build_ytdlp_command must exist on DownloadJob.

    build_ytdlp_command runs outside the task's try/except, so a missing
    attribute kills the asyncio task and the concurrency slot is never
    released - every queued download then hangs forever.
    """
    tree = ast.parse(inspect.getsource(build_ytdlp_command))
    used = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "job"
        ):
            used.add(node.attr)
    declared = set(DownloadJob.__dataclass_fields__)
    missing = used - declared
    check(
        f"build_ytdlp_command job attrs all declared (missing: {sorted(missing)})",
        not missing,
    )
    check("DownloadJob has retries", "retries" in declared)
    check("DownloadJob has fragment_retries", "fragment_retries" in declared)


def test_build_command_with_retries():
    job = DownloadJob(job_id="t", url="https://youtu.be/x", path=str(_ROOT), retries=3)
    cmd = build_ytdlp_command(job)
    check("--retries injected", "--retries" in cmd and "3" in cmd)
    check("retries omitted when None", "--retries" not in build_ytdlp_command(
        DownloadJob(job_id="t", url="https://youtu.be/x", path=str(_ROOT))))


# ---------------------------------------------------------------------------
# 2. Download output path whitelist (arbitrary-file-deletion guard)
# ---------------------------------------------------------------------------

def test_download_path_whitelist():
    allowed, blocked = system_service.is_download_dir_allowed, None
    check("temp download dir allowed", allowed(Path(os.environ.get("TEMP", "/tmp")) / "dl"))
    check("user Downloads allowed", allowed(Path.home() / "Downloads"))
    for bad in ("C:/Windows", "C:/Windows/System32", "C:/Program Files", "/etc", "/usr/bin"):
        check(f"{bad} blocked", not allowed(Path(bad)))
    check("drive root blocked", not allowed(Path("C:/")))
    check("relative path blocked", not allowed(Path("relative/dl")))


# ---------------------------------------------------------------------------
# 3. yt-dlp option blacklist (RCE guard)
# ---------------------------------------------------------------------------

def test_option_blacklist():
    dangerous = {
        "--exec 'rm -rf /'": "--exec",
        "--exec-before-download id": "--exec-before-download",
        "--external-downloader aria2c": "--external-downloader",
        "--config-location /tmp/x.conf": "--config-location",
        "--batch-file list.txt": "--batch-file",
        "--load-info-json i.json": "--load-info-json",
        "--ffmpeg-location /tmp/evil": "--ffmpeg-location",
        "-o /etc/passwd": "-o",
        "--exe whoami": "--exe",  # optparse abbreviation
    }
    for cmd, expect in dangerous.items():
        check(f"blocked: {cmd}", command_service.find_blocked_option(cmd) == expect)

    legitimate = [
        "-f bestvideo+bestaudio",
        "--format 137",
        "--extract-audio --audio-format mp3",
        "--write-subs --sub-langs en",
        "--fragment-retries 5 --retries 5",
        "--download-archive archive.txt",
        "--embed-metadata --embed-chapters",
    ]
    for cmd in legitimate:
        check(f"allowed: {cmd}", command_service.find_blocked_option(cmd) is None)


# ---------------------------------------------------------------------------
# 4. Password hashing
# ---------------------------------------------------------------------------

def test_password_hashing():
    h = _hash_password("correct horse battery staple")
    check("PBKDF2 scheme used", h.startswith("pbkdf2_sha256$"))
    check("correct password verifies", verify_against_hash(h, "correct horse battery staple"))
    check("wrong password rejected", not verify_against_hash(h, "wrong"))
    check("empty hash rejected", not verify_against_hash("", "x"))
    check("legacy sha256 hash still accepted",
          verify_against_hash(_legacy_hash("ytsage"), "ytsage"))
    # Salts must differ between two hashes of the same password.
    check("per-password salt", _hash_password("same") != _hash_password("same"))


# ---------------------------------------------------------------------------
# 5. Token signing
# ---------------------------------------------------------------------------

def test_tokens():
    token = create_token()
    check("fresh token validates", verify_token(token) is not None)
    check("tampered signature rejected", verify_token(token[:-3] + "bad") is None)
    check("garbage rejected", verify_token("not-a-token") is None)


# ---------------------------------------------------------------------------
# 6. Sync centre (dysync parity)
# ---------------------------------------------------------------------------

def test_dedup_priority_normalization():
    """Import/export must not double-encode dedup_priority.

    The old code ran json.dumps on an already-encoded string, so an imported
    profile ended up with a string inside a string and dedup silently broke.
    """
    from webui.sync import store

    as_list = json.loads(store._normalize_dedup_priority(["liked", "playlist"]))
    check("list accepted", as_list == ["liked", "playlist"])

    once = store._normalize_dedup_priority(["liked", "playlist"])
    twice = store._normalize_dedup_priority(once)  # simulate an import
    check("already-encoded string is not re-encoded", json.loads(twice) == ["liked", "playlist"])
    check("round trip is stable", store._normalize_dedup_priority(twice) == once)
    check("None falls back to defaults",
          json.loads(store._normalize_dedup_priority(None)) == store.DEFAULT_DEDUP_PRIORITY)


def test_anti_bot_options():
    from webui.sync.engine import _anti_bot_options, _jitter

    opts = _anti_bot_options({"anti_bot_enabled": True, "sleep_min": 2, "sleep_max": 9,
                              "ua_disguise": True})
    joined = " ".join(opts)
    check("sleep-requests passed", "--sleep-requests" in joined and "2" in joined)
    check("random sleep range passed",
          "--sleep-interval" in joined and "--max-sleep-interval" in joined)
    check("user-agent passed", "--user-agent" in joined)
    check("disabled -> no options", _anti_bot_options({"anti_bot_enabled": False}) == [])
    check("jitter within range",
          2.0 <= _jitter({"anti_bot_enabled": True, "sleep_min": 2, "sleep_max": 9}) <= 9.0)
    check("jitter off when disabled",
          _jitter({"anti_bot_enabled": False, "sleep_min": 2, "sleep_max": 9}) == 0.0)


def test_episode_naming():
    """dysync 合集/短剧: series & mix items get S01E01 style names."""
    from webui.sync.engine import _naming_template
    from webui.sync.nfo_service import _parse_episode

    settings = {"video_naming_template": "%(title)s_[%(id)s].%(ext)s", "episode_naming": True}
    check("series gets S01E prefix",
          _naming_template({}, {"kind": "series"}, settings, 3).startswith("S01E03_"))
    check("mix gets S01E prefix",
          _naming_template({}, {"kind": "mix"}, settings, 12).startswith("S01E12_"))
    check("playlist unaffected",
          _naming_template({}, {"kind": "playlist"}, settings, 3) == "%(title)s_[%(id)s].%(ext)s")
    # dysync: "是否直接用视频标题做文件名"
    check("folder_by_title drops the id",
          _naming_template({"folder_by_title": 1}, {"kind": "playlist"}, settings, 1)
          == "%(title)s.%(ext)s")
    check("episode parsed from file name",
          _parse_episode("/x/S01E07_title_[abc].mp4") == (1, 7))
    check("no episode -> None", _parse_episode("/x/plain title.mp4") is None)


def test_target_kind_validation():
    """mix / series / posts must be accepted, junk must not."""
    from webui.sync.routes import CreateTarget, UpdateTarget

    for kind in ("playlist", "liked", "channel", "subscriptions", "favorites",
                 "mix", "series", "posts"):
        CreateTarget(kind=kind)
    check("all dysync-parity kinds accepted", True)
    try:
        CreateTarget(kind="not_a_kind")
        check("unknown kind rejected", False)
    except Exception:
        check("unknown kind rejected", True)
    try:
        UpdateTarget(kind="not_a_kind")  # used to be unvalidated
        check("UpdateTarget validates kind too", False)
    except Exception:
        check("UpdateTarget validates kind too", True)


# ---------------------------------------------------------------------------
# 7. Database backends + migration (dysync: DatabaseMigrationService)
# ---------------------------------------------------------------------------

def test_dialect_ddl():
    """Each engine needs its own DDL / upsert syntax."""
    from webui.sync import db

    lite, my, pg = (db.get_dialect(n) for n in ("sqlite", "mysql", "postgresql"))

    check("sqlite AUTOINCREMENT", "AUTOINCREMENT" in lite.create_table("profiles"))
    check("mysql AUTO_INCREMENT", "AUTO_INCREMENT" in my.create_table("profiles"))
    check("postgresql SERIAL", "SERIAL" in pg.create_table("profiles"))

    check("sqlite placeholder is ?", lite.placeholder == "?")
    check("mysql placeholder is %s", my.placeholder == "%s")
    check("postgresql placeholder is %s", pg.placeholder == "%s")

    check("sqlite upsert", lite.insert_or_replace("sync_settings", ("key", "value")).startswith("INSERT OR REPLACE"))
    check("mysql upsert", my.insert_or_replace("sync_settings", ("key", "value")).startswith("REPLACE INTO"))
    check("pg upsert uses ON CONFLICT", "ON CONFLICT" in pg.insert_or_replace("sync_settings", ("key", "value")))
    check("pg insert-ignore", "ON CONFLICT DO NOTHING" in pg.insert_or_ignore("excludes", ("video_id",)))
    check("mysql insert-ignore", my.insert_or_ignore("excludes", ("video_id",)).startswith("INSERT IGNORE"))

    # MySQL refuses a DEFAULT on a TEXT column, so short strings become VARCHAR.
    my_ddl = my.create_table("profiles")
    check("mysql keeps DEFAULT on VARCHAR", "dedup_priority VARCHAR(512) DEFAULT" in my_ddl)
    check("mysql TEXT column has no DEFAULT",
          "cookie_check_error TEXT DEFAULT" not in my_ddl)


def test_database_migration():
    """dysync 数据库迁移: copy every table from one backend to another."""
    import shutil
    import tempfile

    from webui.sync import db

    tmp = Path(tempfile.mkdtemp(prefix="ytsage_dbtest_"))
    try:
        src_cfg = {"type": "sqlite", "sqlite_path": str(tmp / "src.db")}
        dst_cfg = {"type": "sqlite", "sqlite_path": str(tmp / "dst.db")}

        src = db.connect(src_cfg)
        db.create_schema(src, db.get_dialect("sqlite"))
        src.execute(
            "INSERT INTO profiles (name, root_path, dedup_priority) VALUES (?,?,?)",
            ("src-profile", str(tmp / "videos"), '["liked","playlist"]'),
        )
        src.execute("INSERT INTO sync_settings (key,value) VALUES (?,?)", ("k1", "v1"))
        src.commit()

        result = db.migrate_data(src_cfg, dst_cfg)
        check("migration succeeded", result.get("ok") is True)
        check("profiles copied", result.get("tables", {}).get("profiles") == 1)
        check("rows counted", (result.get("rows") or 0) >= 2)
        src.close()

        dst = db.connect(dst_cfg)
        rows = db.dict_rows(dst.execute("SELECT name, root_path, dedup_priority FROM profiles"))
        check("row data survived the move",
              bool(rows) and rows[0]["name"] == "src-profile"
              and rows[0]["dedup_priority"] == '["liked","playlist"]')
        settings = db.dict_rows(dst.execute("SELECT key, value FROM sync_settings WHERE key='k1'"))
        check("settings survived the move", settings and settings[0]["value"] == "v1")
        dst.close()

        # Re-running must be an exact copy, not a merge.
        db.migrate_data(src_cfg, dst_cfg)
        dst = db.connect(dst_cfg)
        n = db.dict_rows(dst.execute("SELECT COUNT(*) c FROM profiles"))[0]["c"]
        check("re-migration replaces instead of duplicating", n == 1)
        dst.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    for fn in (
        test_job_fields_cover_command_builder,
        test_build_command_with_retries,
        test_download_path_whitelist,
        test_option_blacklist,
        test_password_hashing,
        test_tokens,
        test_dedup_priority_normalization,
        test_anti_bot_options,
        test_episode_naming,
        test_target_kind_validation,
        test_dialect_ddl,
        test_database_migration,
    ):
        print(f"--- {fn.__name__} ---")
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            _FAILED.append(fn.__name__)
            print(f"  FAIL {fn.__name__} raised: {e}")

    print(f"\n{len(_PASSED)} passed, {len(_FAILED)} failed")
    if _FAILED:
        for name in _FAILED:
            print(f"  - {name}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
