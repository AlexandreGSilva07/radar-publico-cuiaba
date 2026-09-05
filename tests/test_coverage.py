"""Gates de cobertura."""

from pathlib import Path

import pytest

from radar_publico.coverage import reports, require_valid
from radar_publico.state import State, StateError


def test_only_reconciled_complete_run_is_valid(tmp_path: Path) -> None:
    with State(tmp_path / "ops.duckdb") as state:
        run = state.start_run("contratos", 2026, "cycle")
        state.set_coverage(
            run.run_id,
            expected_pages=2,
            collected_pages=2,
            expected_records=170,
            collected_records=170,
            status="complete",
        )
        item = require_valid(state, run.run_id)
        assert item.valid


def test_partial_run_is_rejected(tmp_path: Path) -> None:
    with State(tmp_path / "ops.duckdb") as state:
        run = state.start_run("licitacoes", 2026, "cycle")
        state.set_coverage(
            run.run_id,
            expected_pages=2,
            collected_pages=1,
            expected_records=174,
            collected_records=100,
            status="partial",
        )
        with pytest.raises(StateError, match="incompleta"):
            require_valid(state, run.run_id)
        assert reports(state)[0].status == "partial"
