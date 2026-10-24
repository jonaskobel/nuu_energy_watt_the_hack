"""Verify local sales persistence, private access and demo-only email generation."""
from copy import deepcopy
from http.client import HTTPConnection
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.parse import urlencode
from http.server import ThreadingHTTPServer
import json
import base64
from types import SimpleNamespace
from unittest.mock import Mock
from heat_pump_ready.llm.interfaces import LLMResponse, RunnerError
import re
import unittest

from heat_pump_ready.server import make_handler
from heat_pump_ready.sales import SalesStore, missing_requests
from heat_pump_ready.llm.runners import DisabledRunner
from heat_pump_ready.demo_cases import SYNTHETIC


class SalesTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "sales.sqlite3"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(DisabledRunner(), "disabled", "https://demo.example", self.db_path))
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.cookie = ""

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, method, path, values=None, headers=None):
        body = None
        request_headers = {"Cookie": self.cookie}
        if values is not None:
            if path.startswith("/api/"):
                body = json.dumps(values).encode()
                request_headers["Content-Type"] = "application/json"
            else:
                body = urlencode(values).encode()
                request_headers["Content-Type"] = "application/x-www-form-urlencoded"
        request_headers.update(headers or {})
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.request(method, path, body, request_headers)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read().decode()
        finally:
            connection.close()

    def login(self):
        status, headers, _ = self.request("POST", "/sales/login", {"username": "default", "password": "0000"})
        self.assertEqual(status, 303)
        self.cookie = headers["Set-Cookie"].split(";", 1)[0]
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        return SalesStore(self.db_path).session(self.cookie)

    def submit(self, changes=None):
        facts = deepcopy(SYNTHETIC)
        facts.update(changes or {})
        status, _, body = self.request("POST", "/api/assessments", {"input": facts, "disabled_modules": []})
        self.assertEqual(status, 200, body)
        return json.loads(body)

    def test_sales_data_requires_login_and_bad_password_is_rejected(self):
        self.assertEqual(self.request("GET", "/sales")[0], 303)
        self.assertEqual(self.request("GET", "/api/sales/entries")[0], 401)
        self.assertEqual(self.request("POST", "/sales/login", {"username": "default", "password": "wrong"})[0], 401)
        self.login()
        self.assertEqual(self.request("GET", "/sales")[0], 200)

    def test_assessment_output_and_persistent_entry(self):
        result = self.submit({"contact_email": "kunde@example.com", "location": "Demo München"})
        self.assertEqual(result["metrics"]["heat_load_consumption"]["value"], 9.06)
        entries = SalesStore(self.db_path).entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["inputs"]["contact_email"], "kunde@example.com")
        self.assertNotIn("attachments", entries[0]["inputs"])
        self.assertEqual(entries[0]["result"], result)

    def test_offer_request_updates_only_its_assessment(self):
        status, headers, body = self.request("POST", "/api/assessments", {"input": deepcopy(SYNTHETIC)})
        self.assertEqual(status, 200)
        self.submit()
        contact = {"assessment_token": headers["X-Assessment-Token"], "contact_name": "Demo Kunde", "contact_email": "kunde@example.com", "contact_address": "Musterweg 1, 80331 München"}
        self.assertEqual(self.request("POST", "/api/offer-requests", contact)[0], 200)
        entries = {item["id"]: item for item in SalesStore(self.db_path).entries()}
        self.assertEqual(entries[1]["inputs"]["contact_name"], "Demo Kunde")
        self.assertEqual(entries[1]["inputs"]["contact_email"], "kunde@example.com")
        self.assertEqual(entries[1]["inputs"]["contact_address"], contact["contact_address"])
        self.assertEqual(entries[1]["result"], json.loads(body))
        self.assertNotIn("contact_name", entries[2]["inputs"])
        for changes in ({"assessment_token": "wrong"}, {"contact_name": ""}, {"contact_email": "invalid"}, {"contact_address": ""}):
            self.assertEqual(self.request("POST", "/api/offer-requests", {**contact, **changes})[0], 400)
        status, _, html = self.request("GET", "/")
        self.assertNotIn("E-Mail für Rückfragen", html)
        self.assertGreater(html.index('id="offer-form"'), html.index('id="result-view"'))
        self.login()
        self.assertIn("Demo Kunde", self.request("GET", "/sales/entry/1")[2])

    def test_bill_preview_autofill_preserves_extraction_and_uploads_are_not_saved(self):
        runner = SimpleNamespace(supports_images=True, generate=Mock(side_effect=[
            LLMResponse(json.dumps({"value": 13666, "evidence": "Jahresverbrauch Gas", "confidence": "high"}), "test-api"),
            RunnerError("Empfehlung im Test ohne Modell"),
        ]))
        self.server.RequestHandlerClass = make_handler(runner, "api", "https://demo.example", self.db_path)
        bill = {"name": "bill.jpg", "media_type": "image/jpeg", "category": "bill", "data": base64.b64encode(b'\xff\xd8\xffphoto').decode()}
        status, _, body = self.request("POST", "/api/bill-preview", {"input": {"energy_carrier": "gas", "attachments": [bill]}})
        self.assertEqual(status, 200, body)
        preview = json.loads(body)
        self.assertEqual(preview, {"annual_consumption": 13666, "consumption_unit": "kwh"})
        self.assertEqual(SalesStore(self.db_path).entries(), [])
        result = self.submit({**preview, "attachments": [bill], "heating_connection_images": [{**bill, "category": "pipes"}]})
        self.assertEqual(result["metrics"]["annual_consumption"]["source"], "test-api")
        self.assertTrue(result["metrics"]["annual_consumption"]["uncertainty"])
        self.assertEqual(runner.generate.call_count, 2)
        entry = SalesStore(self.db_path).entries()[0]
        self.assertNotIn("attachments", entry["inputs"])
        self.assertNotIn("heating_connection_images", entry["inputs"])

    def test_bill_preview_disabled_or_unreadable_keeps_value_unknown(self):
        bill = {"name": "bill.jpg", "media_type": "image/jpeg", "category": "bill", "data": base64.b64encode(b'\xff\xd8\xffphoto').decode()}
        self.assertEqual(self.request("POST", "/api/bill-preview", {"input": {"attachments": [bill]}})[0], 503)
        runner = SimpleNamespace(supports_images=True, generate=Mock(return_value=LLMResponse(json.dumps({"value": None, "evidence": "Nicht lesbar", "confidence": "low"}), "test-api")))
        self.server.RequestHandlerClass = make_handler(runner, "api", "https://demo.example", self.db_path)
        self.assertEqual(self.request("POST", "/api/bill-preview", {"input": {"attachments": [bill]}})[0], 422)
        self.assertEqual(self.request("POST", "/api/bill-preview", {"input": {"attachments": []}})[0], 400)

    def test_pipe_preview_selects_each_system_and_preserves_uncertainty(self):
        photo = {"name": "pipes.jpg", "media_type": "image/jpeg", "category": "pipes", "data": base64.b64encode(b'\xff\xd8\xffphoto').decode()}
        for system in ("single-pipe", "two-pipe"):
            runner = SimpleNamespace(supports_images=True, generate=Mock(side_effect=[
                LLMResponse(json.dumps({"value": system, "evidence": "Anschluss auf dem Foto", "confidence": "medium"}), "test-api"),
                RunnerError("Keine Empfehlung im Test"),
            ]))
            self.server.RequestHandlerClass = make_handler(runner, "api", "https://demo.example", self.db_path)
            status, _, body = self.request("POST", "/api/pipe-preview", {"input": {"heating_connection_images": [photo]}})
            self.assertEqual(status, 200, body)
            self.assertEqual(json.loads(body)["pipe_system"], system)
            result = self.submit({"pipe_system": system, "heating_connection_images": [photo]})
            self.assertEqual(result["metrics"]["pipe_system"]["value"], system)
            self.assertTrue(result["metrics"]["pipe_system"]["uncertainty"])
            self.assertEqual(result["metrics"]["pipe_system"]["source"], "test-api")
            self.assertEqual(runner.generate.call_count, 2)
        runner.generate = Mock(return_value=LLMResponse(json.dumps({"value": None, "evidence": "Anschluss verdeckt", "confidence": "low"}), "test-api"))
        self.assertEqual(self.request("POST", "/api/pipe-preview", {"input": {"heating_connection_images": [photo]}})[0], 422)

    def test_priority_first_and_savings_break_ties(self):
        self.submit({"location": "Weniger Ersparnis", "annual_consumption": 20000})
        self.submit({"location": "Mehr Ersparnis", "annual_consumption": 30000})
        self.submit({"location": "Technik offen", "pipe_system": "unknown", "construction_year": None, "annual_consumption": 50000})
        entries = SalesStore(self.db_path).entries()
        self.assertEqual([item["inputs"]["location"] for item in entries], ["Mehr Ersparnis", "Weniger Ersparnis", "Technik offen"])

    def test_demo_email_uses_missing_fields_and_is_idempotent(self):
        self.submit({"investment_eur": "", "subsidy_eur": "", "contact_email": "kunde@example.com"})
        session = self.login()
        values = {"csrf": session["csrf"], "recipient": "kunde@example.com", "request_key": "A" * 32}
        status, headers, _ = self.request("POST", "/sales/entry/1/reminder", values)
        self.assertEqual(status, 303)
        status, _, html = self.request("GET", headers["Location"])
        self.assertEqual(status, 200)
        self.assertIn("Kein echter Versand", html)
        messages = SalesStore(self.db_path).outbox()
        self.assertEqual(len(messages), 1)
        self.assertIn("Investition", messages[0]["body"])
        self.assertIn("Förderung", messages[0]["body"])
        self.assertIn("Guten Tag", messages[0]["body"])
        self.request("POST", "/sales/entry/1/reminder", values)
        self.assertEqual(len(SalesStore(self.db_path).outbox()), 1)

    def test_customer_email_preview_excludes_other_customers(self):
        self.submit({"investment_eur": "", "contact_email": "erster@example.com"})
        self.submit({"investment_eur": "", "contact_email": "zweiter@example.com"})
        session = self.login()
        previews = []
        for entry_id, recipient in [(1, "erster@example.com"), (2, "zweiter@example.com")]:
            status, headers, _ = self.request("POST", f"/sales/entry/{entry_id}/reminder", {"csrf": session["csrf"], "recipient": recipient, "request_key": str(entry_id) * 32})
            self.assertEqual(status, 303)
            previews.append(headers["Location"])
        _, _, preview = self.request("GET", previews[0])
        self.assertIn("erster@example.com", preview)
        self.assertNotIn("zweiter@example.com", preview)
        self.assertEqual(preview.count('<article class="panel detail">'), 1)
        _, _, overview = self.request("GET", "/sales/outbox")
        self.assertIn("erster@example.com", overview)
        self.assertIn("zweiter@example.com", overview)
        self.assertEqual(self.request("GET", "/sales/outbox?created=99999")[0], 404)

    def test_drafts_and_simulated_sent_messages_have_distinct_states(self):
        self.submit({"investment_eur": "", "contact_email": "kunde@example.com"})
        session = self.login()
        self.request("POST", "/sales/entry/1/reminder", {"csrf": session["csrf"], "recipient": "kunde@example.com", "request_key": "C" * 32})
        store = SalesStore(self.db_path)
        self.assertEqual(store.outbox()[0]["status"], "draft")
        self.assertEqual(self.request("POST", "/sales/outbox/1/send-demo", {"csrf": "wrong"})[0], 403)
        status, headers, _ = self.request("POST", "/sales/outbox/1/send-demo", {"csrf": session["csrf"]})
        self.assertEqual(status, 303)
        first_sent_at = store.outbox()[0]["sent_at"]
        self.assertEqual(store.outbox()[0]["status"], "sent_demo")
        self.assertTrue(first_sent_at)
        _, _, preview = self.request("GET", headers["Location"])
        self.assertIn("Abgeschickt (Demo)", preview)
        self.assertNotIn("Demo-Versand simulieren", preview)
        self.request("POST", "/sales/outbox/1/send-demo", {"csrf": session["csrf"]})
        self.assertEqual(store.outbox()[0]["sent_at"], first_sent_at)
        self.assertEqual(self.request("POST", "/sales/outbox/999/send-demo", {"csrf": session["csrf"]})[0], 404)
        _, _, overview = self.request("GET", "/sales/outbox")
        self.assertIn("Entwürfe", overview)
        self.assertIn("Abgeschickt (Demo)", overview)

    def test_missing_email_does_not_create_demo_message(self):
        self.submit({"investment_eur": ""})
        session = self.login()
        status, _, body = self.request("POST", "/sales/entry/1/reminder", {"csrf": session["csrf"], "recipient": "", "request_key": "B" * 32})
        self.assertEqual(status, 400)
        self.assertIn("gültige Kunden-E-Mail", body)
        self.assertEqual(SalesStore(self.db_path).outbox(), [])

    def test_csrf_and_foreign_origin_and_logout(self):
        session = self.login()
        self.assertEqual(self.request("POST", "/sales/logout", {"csrf": "invalid"})[0], 403)
        self.assertEqual(self.request("POST", "/sales/logout", {"csrf": session["csrf"]}, {"Origin": "https://foreign.example"})[0], 403)
        self.assertEqual(self.request("POST", "/sales/logout", {"csrf": session["csrf"]})[0], 303)
        self.assertEqual(self.request("GET", "/api/sales/entries")[0], 401)

    def test_html_escaping_and_public_secure_cookie(self):
        self.submit({"location": '<script>alert("test")</script>', "investment_eur": ""})
        status, headers, _ = self.request("POST", "/sales/login", {"username": "default", "password": "0000"}, {"Host": "demo.example", "Origin": "https://demo.example"})
        self.assertEqual(status, 303)
        self.assertIn("; Secure", headers["Set-Cookie"])
        self.cookie = headers["Set-Cookie"].split(";", 1)[0]
        _, _, body = self.request("GET", "/sales")
        self.assertNotIn('<script>alert("test")</script>', body)
        self.assertIn("&lt;script&gt;", body)

    def test_zero_and_false_are_not_missing(self):
        self.submit({"subsidy_eur": 0, "hot_water_via_heating": False})
        entry = SalesStore(self.db_path).entries()[0]
        self.assertNotIn("Förderung (€)", missing_requests(entry))
        self.assertNotIn("Warmwasser über Heizung", missing_requests(entry))

    def test_login_link_and_result_contact_form(self):
        _, _, body = self.request("GET", "/")
        self.assertIn('href="/sales"', body)
        self.assertIn('name="contact_email"', body)
        source = Path(__file__).parents[1] / "heat_pump_ready/web/index.html"
        html = source.read_text(encoding="utf-8")
        self.assertNotIn('name="contact_email"', html.split('id="result-view"')[0])
        self.assertIn('id="offer-form"', html)


if __name__ == "__main__":
    unittest.main()
