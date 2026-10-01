from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from pno.assistant import Assistant


class MemoryStore:
    def __init__(self, records=None, employees=None, dimensions=None):
        self.data = records or []
        self.roster = employees or []
        self._dimensions = dimensions or {"stores": [], "departments": [], "sections": []}

    def records(
        self,
        kind=None,
        period_from=None,
        period_to=None,
        store=None,
        department=None,
        section=None,
        employee=None,
    ):
        found = []
        for row in self.data:
            if kind and row.get("_kind") != kind:
                continue
            period = str(row.get("date") or row.get("_period") or "")
            if period_from and period[:10] < str(period_from)[:10]:
                continue
            if period_to and period[:10] > str(period_to)[:10]:
                continue
            if store and row.get("store") != store:
                continue
            if department and row.get("department") != department:
                continue
            if section and row.get("section") != section:
                continue
            if employee and row.get("employee_id") != employee:
                continue
            found.append(dict(row))
        return found

    def employees(self, period=None):
        return [dict(person) for person in self.roster]

    def dimensions(self):
        return self._dimensions


def record(kind, period, **values):
    return {
        "_kind": kind,
        "_period": period,
        "_import_id": 19,
        "_source": "local.xlsx",
        "_sheet": "Sales",
        **values,
    }


def test_query_interprets_employee_date_store_and_section_overrides_with_citation():
    roster = [{
        "employee_id": "SM-42",
        "employee_name": "Taylor Example",
        "designation": "Section Manager",
        "store": "North",
        "department": "Fashion",
        "section": "Apparel",
    }]
    store = MemoryStore(
        records=[
            record("sales_daily", "2025-08-04", date="2025-08-04", store="North", department="Fashion", section="Apparel", actual=75, budget=100, last_year=50),
            record("sales_daily", "2025-08-04", date="2025-08-04", store="South", department="Fashion", section="Apparel", actual=900, budget=1000, last_year=800),
        ],
        employees=roster,
        dimensions={"stores": ["North", "South"], "departments": ["Fashion"], "sections": ["Apparel"]},
    )
    answer = Assistant(store).ask(
        "daily sales for SM-42 at North section Apparel on 2025-08-04"
    )
    assert "Offline assistant — deterministic analysis" in answer
    assert "Employee lookup: SM-42" in answer
    assert "2025-08-04 to 2025-08-04" in answer
    assert "Actual: 75.00" in answer
    assert "local.xlsx" in answer
    assert "sales_daily" in answer


def test_ambiguous_employee_name_requests_unique_code():
    store = MemoryStore(employees=[
        {"employee_id": "A1", "employee_name": "Alex Smith", "designation": "Associate", "store": "North"},
        {"employee_id": "B2", "employee_name": "Alex Smith", "designation": "Associate", "store": "South"},
    ])
    answer = Assistant(store).ask("find Alex Smith", filters={"employee": "A1"})
    assert "Ambiguous employee match" in answer
    assert "A1" in answer and "B2" in answer


def test_unknown_explicit_employee_query_never_falls_back_to_location_totals():
    store = MemoryStore(
        records=[
            record("sales_mtd", "2025-02-01", store="North", actual=10, budget=10, last_year=8),
            record("sales_mtd", "2025-02-01", store="South", actual=20, budget=20, last_year=16),
        ],
        employees=[{"employee_id": "KNOWN1", "employee_name": "Known Person", "designation": "Associate", "store": "North"}],
        dimensions={"stores": ["North", "South"], "departments": [], "sections": []},
    )
    answer = Assistant(store).ask(
        "sales for employee ID UNKNOWN9",
        filters={"employee": "KNOWN1"},
    )
    assert "No matching employee 'UNKNOWN9'" in answer
    assert "No all-location analysis was run." in answer
    assert "Actual:" not in answer


@pytest.mark.parametrize(
    "question",
    (
        "sales for employee 99999",
        "sales for employee99999",
        "employee 99999",
    ),
)
def test_unknown_numeric_employee_intent_never_falls_back_to_country_totals(question):
    store = MemoryStore(
        records=[
            record("sales_mtd", "2025-02-01", country="Exampleland", actual=100, budget=100, last_year=80),
        ],
        dimensions={"countries": ["Exampleland"], "stores": [], "departments": [], "sections": []},
    )
    answer = Assistant(store).ask(question, filters={"country": "Exampleland"})
    assert "No matching employee '99999'" in answer
    assert "No all-location analysis was run." in answer
    assert "Actual:" not in answer


def test_explicit_question_employee_overrides_ui_employee_filter_with_disclosure():
    store = MemoryStore(
        records=[
            record("sales_mtd", "2025-02-01", store="North", actual=10, budget=10, last_year=8),
            record("sales_mtd", "2025-02-01", store="South", actual=20, budget=20, last_year=16),
        ],
        employees=[
            {"employee_id": "E1", "employee_name": "North Staff", "designation": "Associate", "store": "North"},
            {"employee_id": "E2", "employee_name": "South GM", "designation": "GM", "store": "South"},
        ],
        dimensions={"stores": ["North", "South"], "departments": [], "sections": []},
    )
    answer = Assistant(store).ask("sales for employee E2 at South", filters={"employee": "E1"})
    assert "overrides UI employee filter 'E1'" in answer
    assert "Actual: 20.00" in answer


def test_assistant_does_not_treat_missing_facts_as_zero_and_cites_empty_sources():
    answer = Assistant(MemoryStore()).ask("what are sales?")
    assert "Actual: unavailable" in answer
    assert "No matching sales data" in answer
    assert "Sources: no matching active local imports." in answer


def test_selected_missing_model_is_reported_not_downloaded(tmp_path):
    missing = tmp_path / "not-installed.gguf"
    answer = Assistant(MemoryStore(), model_path=missing).ask("sales")
    assert "Local model unavailable:" in answer
    assert "does not exist" in answer


class FakeChatModel:
    def __init__(self, text):
        self.text = text
        self.call = None

    def create_chat_completion(self, **kwargs):
        self.call = kwargs
        return {"choices": [{"message": {"content": self.text}}]}


def _model_test_store():
    return MemoryStore(
        records=[
            record(
                "sales_mtd",
                "2026-08-01",
                actual=10500,
                budget=10000,
                last_year=9000,
            )
        ],
        dimensions={"countries": [], "stores": [], "departments": [], "sections": []},
    )


def test_local_model_uses_chat_template_and_only_qualitative_python_facts():
    model = FakeChatModel("Sales were above budget and grew year over year.")
    assistant = Assistant(_model_test_store(), model_path="selected.gguf")
    assistant._model = model
    assistant._model_attempted = True

    answer = assistant.ask("Summarize monthly performance in 2026-08")

    assert model.call is not None
    assert model.call["messages"][0]["role"] == "system"
    assert model.call["messages"][1]["role"] == "user"
    prompt = "\n".join(message["content"] for message in model.call["messages"])
    assert "Sales versus budget: above" in prompt
    assert "Sales versus last year: grew" in prompt
    assert "Attendance evidence: unavailable" in prompt
    assert "10500" not in prompt and "10000" not in prompt and "9000" not in prompt
    assert "2026-08" not in prompt
    assert "Actual: 10,500.00" in answer
    assert "Budget: 10,000.00" in answer
    assert "Local model wording (unverified; review before sharing" in answer


@pytest.mark.parametrize(
    "generated",
    (
        "Sales were above budget and grew 10% year over year.",
        "Sales were above budget and grew year over year because of a promotion.",
    ),
)
def test_unsafe_model_wording_is_rejected_without_relaxing_numeric_guard(generated):
    model = FakeChatModel(generated)
    assistant = Assistant(_model_test_store(), model_path="selected.gguf")
    assistant._model = model
    assistant._model_attempted = True

    answer = assistant.ask("Summarize monthly performance in 2026-08")

    assert "Local model summary unavailable: generated wording was rejected by safety validation." in answer
    assert "Local model unavailable:" not in answer
    assert "Actual: 10,500.00" in answer


def test_local_model_loader_is_configured_for_four_thread_cpu_inference(tmp_path, monkeypatch):
    model_path = tmp_path / "small.gguf"
    model_path.write_bytes(b"model fixture")
    created = {}

    def fake_llama(**kwargs):
        created.update(kwargs)
        return object()

    monkeypatch.setitem(sys.modules, "llama_cpp", SimpleNamespace(Llama=fake_llama))
    assistant = Assistant(_model_test_store(), model_path=model_path)

    assert assistant._load_model() is not None
    assert created["n_threads"] == 4
    assert created["n_ctx"] == 2048
    assert created["n_gpu_layers"] == 0