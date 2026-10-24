"""Verify local sales persistence, private access and demo-only email generation."""
from copy import deepcopy
from http.client import HTTPConnection
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.parse import urlencode
from http.server import ThreadingHTTPServer
import json
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

    def test_priority_first_and_savings_break_ties(self):
        self.submit({"location": "Weniger Ersparnis", "annual_consumption": 20000})
        self.submit({"location": "Mehr Ersparnis", "annual_consumption": 30000})
        self.submit({"location": "Technik offen", "pipe_system": "unknown", "annual_consumption": 50000})
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

    def test_login_and_email_input_are_injected_without_editing_assets(self):
        _, _, body = self.request("GET", "/")
        self.assertIn('href="/sales"', body)
        self.assertIn('name="contact_email"', body)
        source = Path(__file__).parents[1] / "heat_pump_ready/web/index.html"
        self.assertNotIn('name="contact_email"', source.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
