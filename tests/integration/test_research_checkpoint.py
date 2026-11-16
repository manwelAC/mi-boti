import importlib.util
from pathlib import Path

from test_evidence_reader import seed_evidence


def checker():
    spec = importlib.util.spec_from_file_location("research_checkpoint", Path(__file__).resolve().parents[2] / "scripts/check_research_prerequisites.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_checkpoint_is_read_only_and_never_claims_live_acceptance(database):
    seed_evidence(database)
    from mi_boti.domain.values import utc_now
    database.connection.execute("INSERT INTO guild_config VALUES ('guild','123456789012345678','READY',1,'{}',?)", (utc_now(),))
    before = list(database.connection.iterdump())
    result = checker().inspect_database(database.path)
    assert result["local_checkpoint_passed"] is True
    assert result["full_phase4a_accepted"] is False
    assert result["evidence"] == result["excerpt_hashes"] == 1
    assert result["unexpired_review_records"] == 0
    assert before == list(database.connection.iterdump())


def test_checkpoint_fails_for_corruption_and_missing_database(database, tmp_path, capsys):
    identifier, _ = seed_evidence(database)
    database.connection.execute("UPDATE evidence SET extracted_fact=extracted_fact||'bad' WHERE id=?", (identifier,))
    assert checker().main(["--database", str(database.path)]) == 2
    assert '"full_phase4a_accepted": false' in capsys.readouterr().out
    missing = tmp_path / "missing.sqlite3"
    assert checker().main(["--database", str(missing)]) == 2
    assert not missing.exists()
