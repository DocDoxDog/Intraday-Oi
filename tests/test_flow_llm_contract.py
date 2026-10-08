import json
from pathlib import Path

from src.llm_gateway import _schema_for_task, _skill_for_task


ROOT = Path(__file__).resolve().parents[1]


def test_flow_analyst_schema_is_canonical():
    schema = _schema_for_task("market.flow_analysis_v1")
    assert schema is not None
    assert schema["additionalProperties"] is False
    assert "structural_path" in schema["properties"]
    assert "evidence_ledger" in schema["properties"]


def test_flow_analyst_skill_is_loaded_from_repository():
    skill = _skill_for_task("market.flow_analysis_v1")
    assert skill
    assert "CONDITIONAL PATH" in skill
    assert "Never fabricate Actual/Forecast/Previous" in skill


def test_flow_schema_file_exists():
    path = ROOT / "schemas" / "llm" / "flow_market_analyst_v1.json"
    assert path.is_file()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["type"] == "object"
