"""Ask PNO: the built-in assistant, the confirm-before-saving flow, the read-only SQL guard and the AI tool loop
(against a fake OpenAI-compatible server, so no key or internet is needed)."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from pno import engine
from pno.agent import llm


def ask(api, q, **kw):
    r = api.dispatch("agent_ask", {"question": q, "month": "2026-09", **kw})
    assert "error" not in r, r
    return r


@pytest.mark.parametrize("q, must", [
    ("Top 5 section managers in Lahore", "Top 5 section managers in Lahore"),
    ("bottom 3 department heads", "Bottom 3 department heads"),
    ("How is attendance?", "Real absence"),
    ("Which punches need fixing?", "missing punches"),
    ("How are the stores doing?", "Store league"),
    ("Show me the trend", "trend"),
])
def test_basic_assistant_answers(api, q, must):
    r = ask(api, q)
    assert r["engine"] == "basic"
    text = r["answer"] + " " + " ".join(b.get("title", "") for b in r["blocks"])
    assert must.lower() in text.lower()


def test_basic_person_and_store(api, db):
    mm = engine.model(db, "2026-09")
    p = next(p for p in mm.people.values() if p.role == "SM" and p.score is not None)
    r = ask(api, f"How is {p.name} doing?")
    assert p.name in r["answer"] and any(b["title"] == "How the score is made" for b in r["blocks"] if b["type"] == "table")
    r = ask(api, "Tell me about Fortress")
    assert "Fortress" in r["answer"]


def test_leave_is_only_saved_after_confirm(api, db):
    mm = engine.model(db, "2026-09")
    p = next(p for p in mm.people.values() if p.att and p.att["absent"] >= 1)
    d = next(c["day"] for c in p.att["calendar"] if c["kind"] == "absent")
    n0 = db.val("SELECT COUNT(*) FROM leaves")
    r = ask(api, f"{p.emp} was on sick leave on {d}")
    assert r["actions"], r["answer"]
    assert db.val("SELECT COUNT(*) FROM leaves") == n0                    # nothing saved yet
    c = api.dispatch("agent_confirm", {"action_id": r["actions"][0]["id"]})
    assert c["ok"] and db.val("SELECT COUNT(*) FROM leaves") == n0 + 1
    assert api.dispatch("agent_confirm", {"action_id": r["actions"][0]["id"]})["ok"] is False   # only once
    assert engine.model(db, "2026-09").people[p.emp].att["absent"] == p.att["absent"] - 1


def test_holiday_cancel_changes_nothing(api, db):
    r = ask(api, "Add 15 September 2026 as Test Day holiday")
    assert r["actions"]
    api.dispatch("agent_confirm", {"action_id": r["actions"][0]["id"], "approve": False})
    assert not db.q1("SELECT 1 FROM holidays WHERE day='2026-09-15'")


def test_sql_sandbox_reads_but_never_writes(api, db):
    svc = api.agent
    from pno.agent.tools import Toolbox
    tb = Toolbox(svc, "2026-09", {}, False)
    ok = tb.t_sql("SELECT role, COUNT(*) FROM people GROUP BY role ORDER BY 2 DESC")
    assert ok["rows"] and "error" not in ok
    assert tb.t_sql("SELECT COUNT(*) FROM sales")["rows"][0][0] > 0
    for bad in ["DELETE FROM roster", "DROP TABLE roster", "SELECT 1; DELETE FROM roster", "UPDATE stores SET name='x'",
                "WITH x AS (SELECT 1) DELETE FROM roster", "ATTACH DATABASE 'x.db' AS x", "PRAGMA writable_schema=1"]:
        assert "error" in tb.t_sql(bad), bad
    assert db.val("SELECT COUNT(*) FROM roster") > 0


def test_anonymise_hides_names_from_the_ai_and_restores_them(api, db):
    from pno.agent.tools import Toolbox
    tb = Toolbox(api.agent, "2026-09", {}, True)
    rows = tb.t_sql("SELECT name FROM people LIMIT 5")["rows"]
    assert all(r[0].startswith("Employee ") for r in rows)


# ------------------------------------------------------------------ fake OpenAI-compatible server
class Fake:
    script: list = []
    seen: list = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        self._send(200, {"data": [{"id": "llama-3.3-70b-versatile"}, {"id": "whisper-large-v3"}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Fake.seen.append({"auth": self.headers.get("Authorization"), "body": body})
        status, payload = Fake.script.pop(0)
        self._send(status, payload)

    def _send(self, status, payload):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture
def fake_groq(monkeypatch):
    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(llm, "GROQ_URL", f"http://127.0.0.1:{srv.server_port}/v1")
    Fake.script, Fake.seen = [], []
    yield Fake
    srv.shutdown()


def msg(content=None, calls=None):
    m = {"role": "assistant", "content": content}
    if calls:
        m["tool_calls"] = [{"id": f"c{i}", "type": "function", "function": {"name": n, "arguments": json.dumps(a)}}
                           for i, (n, a) in enumerate(calls)]
    return 200, {"choices": [{"message": m}]}


def test_groq_tool_loop(api, fake_groq):
    api.dispatch("agent_settings", {"mode": "groq", "key": "gsk_test_key_123456"})
    st = api.dispatch("agent_status", {})
    assert st["active"] == "groq" and st["key_masked"].startswith("gsk_") and "test_key" not in st["key_masked"]
    fake_groq.script = [
        msg(calls=[("find_people", {"role": "SM", "limit": 3}),
                   ("chart", {"kind": "hbar", "title": "Top SMs", "labels": ["a", "b"], "series": [{"name": "Score", "values": [8, 7]}]})]),
        msg("The top section managers are listed below."),
    ]
    r = ask(api, "Who are the best section managers?")
    assert r["engine"] == "groq" and r["answer"].startswith("The top section managers")
    assert r["tools"] == ["find_people", "chart"]
    assert any(b["type"] == "chart" for b in r["blocks"])
    first, second = fake_groq.seen
    assert first["auth"] == "Bearer gsk_test_key_123456" and first["body"]["tools"]
    tool_msgs = [m for m in second["body"]["messages"] if m["role"] == "tool"]
    assert len(tool_msgs) == 2 and "people" in tool_msgs[0]["content"]


def test_groq_proposal_still_needs_confirm(api, db, fake_groq):
    api.dispatch("agent_settings", {"mode": "groq", "key": "gsk_test_key_123456"})
    fake_groq.script = [msg(calls=[("propose_holiday", {"day": "2026-09-16", "name": "Test"})]), msg("Prepared. Please confirm.")]
    r = ask(api, "mark 16 sept as a holiday")
    assert r["actions"] and not db.q1("SELECT 1 FROM holidays WHERE day='2026-09-16'")
    api.dispatch("agent_confirm", {"action_id": r["actions"][0]["id"]})
    assert db.q1("SELECT 1 FROM holidays WHERE day='2026-09-16'")


def test_groq_failure_falls_back_to_built_in(api, fake_groq):
    api.dispatch("agent_settings", {"mode": "groq", "key": "gsk_bad_key_123456"})
    fake_groq.script = [(401, {"error": {"message": "Invalid API Key"}})]
    r = ask(api, "How is attendance?")
    assert r["engine"] == "basic" and "not accepted" in r["answer"] and "Real absence" in r["answer"]


def test_groq_test_button(api, fake_groq):
    api.dispatch("agent_settings", {"mode": "auto", "key": "gsk_test_key_123456"})
    fake_groq.script = [msg("OK")]
    r = api.dispatch("agent_test", {})
    assert r["ok"] and "llama-3.3-70b-versatile" in r["models"] and "whisper-large-v3" not in r["models"]


def test_key_can_be_cleared(api):
    api.dispatch("agent_settings", {"key": "gsk_test_key_123456"})
    api.dispatch("agent_settings", {"clear_key": True})
    assert api.dispatch("agent_status", {})["active"] in ("basic", "offline")


def test_leave_file_dropped_in_chat(api, db, tmp_path, demo):
    p = tmp_path / "Leave Register Sep 2026.xlsx"
    p.write_bytes(demo.files["Leave Register Sep 2026.xlsx"])
    r = api.dispatch("agent_ask", {"question": "", "month": "2026-09", "attachments": [str(p)]})
    assert "Leave register" in r["answer"]
    assert r["actions"] and r["actions"][0]["kind"] == "import"
    c = api.dispatch("agent_confirm", {"action_id": r["actions"][0]["id"]})
    assert c["ok"]


# ------------------------------------------------------------------ offline AI (a stand-in llama-server on this PC)
FAKE_LLAMA = r'''#!{py}
import json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
port = int(sys.argv[sys.argv.index("--port") + 1])
assert "--jinja" in sys.argv and "-m" in sys.argv
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, obj):
        d = json.dumps(obj).encode(); self.send_response(200); self.send_header("Content-Length", str(len(d))); self.end_headers(); self.wfile.write(d)
    def do_GET(self): self._send({{"status": "ok"}})
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if any(m["role"] == "tool" for m in body["messages"]):
            m = {{"role": "assistant", "content": "Offline answer from the tools."}}
        else:
            m = {{"role": "assistant", "content": None, "tool_calls": [{{"id": "a", "type": "function",
                 "function": {{"name": "overview", "arguments": "{{}}"}}}}]}}
        self._send({{"choices": [{{"message": m}}]}})
print("server is listening", flush=True)
HTTPServer(("127.0.0.1", port), H).serve_forever()
'''


def test_offline_ai_starts_and_answers(api, tmp_path, monkeypatch):
    import sys

    from pno.agent import local
    exe = tmp_path / ("llama-server.exe" if sys.platform == "win32" else "llama-server")
    exe.write_text(FAKE_LLAMA.format(py=sys.executable))
    exe.chmod(0o755)
    if sys.platform == "win32":
        pytest.skip("the stand-in server is a script; the Windows build checks the real llama-server instead")
    monkeypatch.setattr(local, "find_runtime", lambda: exe)
    monkeypatch.setattr(local, "PORT", 18299)
    model = tmp_path / "tiny.gguf"
    model.write_bytes(b"GGUF")
    api.dispatch("agent_settings", {"mode": "offline", "clear_key": True})
    assert api.agent.offline_link(str(model))["model"] == str(model)
    assert api.dispatch("agent_status", {})["active"] == "offline"
    try:
        r = ask(api, "How are we doing?")
        assert r["engine"] == "offline" and r["answer"] == "Offline answer from the tools." and r["tools"] == ["overview"]
        assert local.SERVER.ready()
    finally:
        local.SERVER.stop()
    assert not local.SERVER.ready()
