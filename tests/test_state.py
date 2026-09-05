"""Estado, idempotência e checkpoint."""

from pathlib import Path

import pytest

from radar_publico.state import State, StateError


def test_cycles_are_idempotent_and_new_cycle_creates_run(tmp_path: Path) -> None:
    with State(tmp_path / "ops.duckdb") as state:
        first = state.start_run("contratos", 2026, "daily-1")
        repeated = state.start_run("contratos", 2026, "daily-1")
        newer = state.start_run("contratos", 2026, "daily-2")

        assert first.run_id == repeated.run_id
        assert first.run_id != newer.run_id


def test_checkpoint_uses_completed_prefix(tmp_path: Path) -> None:
    with State(tmp_path / "ops.duckdb") as state:
        run = state.start_run("contratos", 2026, "cycle")
        request = state.start_request(run.run_id, 0)
        object_id = state.record_object("hash", "bronze/a.json.gz")
        state.complete_page(request, object_id=object_id, record_count=100, total_records=170)

        assert state.next_page(run.run_id) == 1
        assert state.progress(run.run_id) == (1, 100, 170)


def test_invalid_terminal_status_is_rejected(tmp_path: Path) -> None:
    with State(tmp_path / "ops.duckdb") as state:
        run = state.start_run("contratos", 2026, "cycle")
        with pytest.raises(StateError):
            state.finish_run(run.run_id, "complete")


def test_migration_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "ops.duckdb"
    with State(path):
        pass
    with State(path) as state:
        assert state.db.execute("SELECT count(*) FROM schema_migration").fetchone()[0] == 1
