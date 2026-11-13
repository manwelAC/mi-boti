import importlib
import pkgutil
import sqlite3
import subprocess
import sys

import pytest

from mi_boti.__main__ import main
from mi_boti.config import load_settings
from mi_boti.domain.errors import DatabaseError
from mi_boti.runtime import initialize


def test_check_config_is_offline_and_does_not_create_data(configured, monkeypatch, capsys):
    env, _ = configured
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert main(["check-config"]) == 0
    assert '"ai_enabled": false' in capsys.readouterr().out
    from pathlib import Path
    assert not Path(env["MI_BOTI_DATA_DIR"]).exists()


def test_startup_initializes_persistence_without_discord_or_workers(configured, monkeypatch):
    settings = load_settings(configured[0])
    import socket
    monkeypatch.setattr(socket, "create_connection", lambda *_: pytest.fail("network launched"))
    with initialize(settings) as db:
        assert db.connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert db.connection.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0
        assert db.connection.execute("SELECT count(*) FROM hunts").fetchone()[0] == 0
    with initialize(settings) as db:
        assert db.connection.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0


def test_changed_guild_refused_and_cli_errors_do_not_disclose_token(configured, monkeypatch, capsys):
    env, _ = configured
    with initialize(load_settings(env)):
        pass
    with pytest.raises(DatabaseError):
        with initialize(load_settings({**env, "MI_BOTI_GUILD_ID": "999"})):
            pass
    for key, value in {**env, "MI_BOTI_GUILD_ID": "999", "MI_BOTI_DISCORD_TOKEN": "private-test-token"}.items():
        monkeypatch.setenv(key, value)
    assert main(["init-db"]) == 2
    output = capsys.readouterr()
    assert "private-test-token" not in output.err
    assert "DATABASE_ERROR" in output.err


def test_importing_all_modules_has_no_database_network_or_process_side_effects():
    script = """
import socket,subprocess,sqlite3,pkgutil,importlib
def forbidden(*args,**kwargs): raise AssertionError('import side effect')
socket.socket.connect=forbidden
class ForbiddenPopen(subprocess.Popen):
 def __init__(self,*args,**kwargs): forbidden()
subprocess.Popen=ForbiddenPopen
sqlite3.connect=forbidden
import mi_boti
for item in pkgutil.walk_packages(mi_boti.__path__,mi_boti.__name__+'.'):
 importlib.import_module(item.name)
print('imports safe')
"""
    completed = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=15)
    assert completed.returncode == 0, completed.stderr
    assert "imports safe" in completed.stdout
