"""Server-rendered sales pages, private sessions and persistent assessment records."""
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
from http.cookies import SimpleCookie, CookieError
from pathlib import Path
import json
import math
import secrets
import sqlite3
import time

COOKIE_NAME = "waermeweise_sales"
SESSION_SECONDS = 8 * 60 * 60
PRIORITIES = {0: ("A", "Hohe Priorität"), 1: ("B", "Potenzial prüfen"), 2: ("C", "Klärungsbedarf"), 3: ("D", "Geringe Priorität")}
LABELS = {"construction_year": "Baujahr", "floor_area_m2": "Wohnfläche (m²)", "renovation_status": "Sanierungsstand", "annual_consumption": "Jahresverbrauch", "consumption_unit": "Verbrauchseinheit", "energy_carrier": "Energieträger", "persons_in_household": "Personen", "hot_water_via_heating": "Warmwasser über Heizung", "heat_distribution": "Heizflächen", "pipe_system": "Rohrsystem", "flow_temperature_c": "Vorlauftemperatur (°C)", "investment_eur": "Investition (€)", "subsidy_eur": "Förderung (€)", "horizon_years": "Zeitraum (Jahre)", "location": "Region", "notes": "Hinweise"}
LABELS["contact_email"] = "Kunden-E-Mail"


class SalesStore:
    """Use one short-lived SQLite connection per request; never save uploaded files."""
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS entries (id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT NOT NULL, inputs TEXT NOT NULL, result TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, csrf TEXT NOT NULL, expires REAL NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS outbox (id INTEGER PRIMARY KEY AUTOINCREMENT, entry_id INTEGER NOT NULL, created TEXT NOT NULL, recipient TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL, request_key TEXT NOT NULL UNIQUE)")

    def connect(self):
        db = sqlite3.connect(str(self.path), timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def save(self, user_input, result, contact_email=""):
        """Persist validated scalar facts and existing outputs, excluding attachment bytes."""
        inputs = {name: getattr(user_input, name) for name in user_input.__dataclass_fields__ if name != "attachments"}
        inputs["contact_email"] = contact_email
        created = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with closing(self.connect()) as db, db:
            db.execute("INSERT INTO entries(created,inputs,result) VALUES(?,?,?)", (created, json.dumps(inputs, ensure_ascii=False), json.dumps(result, ensure_ascii=False, allow_nan=False)))

    def entries(self):
        """Return every stored entry ordered by the documented sales criteria."""
        with closing(self.connect()) as db:
            rows = db.execute("SELECT * FROM entries ORDER BY id DESC").fetchall()
        entries = [{"id": row["id"], "created": row["created"], "inputs": json.loads(row["inputs"]), "result": json.loads(row["result"])} for row in rows]
        for entry in entries:
            entry["priority"], entry["reason"] = priority(entry["result"])
        return sorted(entries, key=rank_key)

    def create_reminder(self, entry, recipient, request_key):
        """Create an idempotent local demo email. No external delivery takes place."""
        missing = missing_requests(entry)
        if not missing:
            raise ValueError("Für diesen Check fehlen keine der erfassten Kernangaben.")
        subject = "Ihr Wärmepumpen-Check: ein paar Angaben fehlen noch"
        body = ("Guten Tag,\n\nvielen Dank für Ihr Interesse an einer Wärmepumpe und für Ihre bisherigen Angaben. "
                "Damit wir Ihre Situation besser einschätzen und das Beratungsgespräch gut vorbereiten können, "
                "würden wir uns noch über folgende Informationen freuen:\n\n"
                + "\n".join("• " + item for item in missing)
                + "\n\nWenn Ihnen einzelne Angaben nicht vorliegen, ist das kein Problem. "
                "Geben Sie uns gern kurz Bescheid – wir klären die offenen Punkte gemeinsam. "
                "Sie können diese Informationen im nächsten Gespräch nachreichen.\n\n"
                "Vielen Dank für Ihre Unterstützung!\n\nFreundliche Grüße\nIhr Wärmeweise-Team\n\n"
                "Referenz: Wärmepumpen-Check #" + str(entry["id"]).zfill(5))
        with closing(self.connect()) as db, db:
            db.execute("INSERT OR IGNORE INTO outbox(entry_id,created,recipient,subject,body,request_key) VALUES(?,?,?,?,?,?)", (entry["id"], datetime.now(timezone.utc).isoformat(timespec="seconds"), recipient, subject, body, request_key))
            row = db.execute("SELECT * FROM outbox WHERE request_key=?", (request_key,)).fetchone()
            return dict(row)

    def outbox(self):
        with closing(self.connect()) as db:
            return [dict(row) for row in db.execute("SELECT * FROM outbox ORDER BY id DESC").fetchall()]

    def create_session(self):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        with closing(self.connect()) as db, db:
            db.execute("DELETE FROM sessions WHERE expires <= ?", (time.time(),))
            db.execute("INSERT INTO sessions VALUES(?,?,?)", (sha256(token.encode()).hexdigest(), csrf, time.time() + SESSION_SECONDS))
        return token

    def session(self, cookie_header):
        try:
            cookie = SimpleCookie()
            cookie.load(cookie_header or "")
            token = cookie[COOKIE_NAME].value if COOKIE_NAME in cookie else ""
        except CookieError:
            return None
        if not token or len(token) > 200:
            return None
        digest = sha256(token.encode()).hexdigest()
        with closing(self.connect()) as db:
            row = db.execute("SELECT token_hash,csrf FROM sessions WHERE token_hash=? AND expires>?", (digest, time.time())).fetchone()
        return dict(row) if row else None

    def logout(self, session):
        with closing(self.connect()) as db, db:
            db.execute("DELETE FROM sessions WHERE token_hash=?", (session["token_hash"],))


def metric(result, key):
    item = result.get("metrics", {}).get(key) or {}
    value = item.get("value")
    return value if item.get("status") == "available" and isinstance(value, (int, float)) and math.isfinite(value) else None


def priority(result):
    """Classify sales follow-up only; leave all technical and financial results untouched."""
    decision = result.get("decision", {})
    if decision.get("validation_issues"):
        return 3, "Widersprüchliche Angaben zuerst klären."
    if decision.get("verdict") == "not_worthwhile" or decision.get("readiness") == "red":
        return 3, "Wirtschaftlichkeit negativ oder technische Belege unzureichend."
    if decision.get("readiness") == "green":
        if decision.get("verdict") == "worthwhile":
            return 0, "Technisch geeignet und im bestehenden Modell wirtschaftlich."
        return 1, "Technisch geeignet; wirtschaftliche Beurteilung noch offen."
    return 2, "Technische Fragen vor einer Empfehlung klären."


def rank_key(entry):
    savings = metric(entry["result"], "annual_savings")
    payback = metric(entry["result"], "payback_period")
    return (entry["priority"], savings is None, -(savings or 0), payback is None, payback if payback is not None else math.inf, -entry["id"])


def missing_requests(entry):
    """List unknown core customer facts; preserve valid zero and false answers."""
    facts = entry["inputs"]
    needed = ["construction_year", "floor_area_m2", "renovation_status", "annual_consumption", "persons_in_household", "hot_water_via_heating", "heat_distribution", "pipe_system", "investment_eur", "subsidy_eur"]
    if facts.get("heat_distribution") != "underfloor":
        needed.append("flow_temperature_c")
    return [LABELS[key] for key in needed if facts.get(key) is None or facts.get(key) in ("", "unknown")]


def text(value):
    if value is None or value == "":
        return "Noch offen"
    if isinstance(value, bool):
        return "Ja" if value else "Nein"
    if isinstance(value, (int, float)):
        return f"{value:,.1f}".replace(",", "_").replace(".", ",").replace("_", ".")
    if isinstance(value, list):
        return " – ".join(text(item) for item in value)
    return {"gas": "Gas", "oil": "Heizöl", "lpg": "Flüssiggas", "radiators": "Heizkörper", "underfloor": "Fußbodenheizung", "mixed": "Gemischt", "unknown": "Unbekannt", "two-pipe": "Zweirohr", "single-pipe": "Einrohr"}.get(str(value), str(value))


def page(title, content, session=None):
    logout = ""
    if session:
        logout = '<a href="/sales/outbox">Demo-Postausgang</a><form action="/sales/logout" method="post"><input type="hidden" name="csrf" value="' + escape(session["csrf"], quote=True) + '"><button class="button secondary">Abmelden</button></form>'
    return ('<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + escape(title) + ' · Wärmeweise</title><link rel="stylesheet" href="/sales/style.css"></head><body><header><a class="brand" href="/">w° <span>wärmeweise</span></a><nav><a href="/">Zum Wärmepumpen-Check</a>' + logout + '</nav></header><main>' + content + '</main><footer>Wärmeweise · Vertriebsbereich · Demo-Ranking auf Grundlage vorhandener Ergebnisse</footer></body></html>').encode()


def login_page(error=""):
    error_html = '<p role="alert" class="error">' + escape(error) + '</p>' if error else ""
    content = '<section class="login"><span class="eyebrow">VERTRIEBSBEREICH</span><h1>Gute Chancen.<br>Im richtigen Blick.</h1><p>Melde dich an, um eingegangene Checks und ihre Priorität zu sehen.</p><form action="/sales/login" method="post"><label>Benutzername<input name="username" autocomplete="username" maxlength="100" required autofocus></label><label>Passwort<input type="password" name="password" autocomplete="current-password" maxlength="200" required></label>' + error_html + '<button class="button primary">Anmelden <span>→</span></button></form><p class="fine">Zugang zur internen Demo-Vertriebsübersicht.</p></section>'
    return page("Vertriebslogin", content)


def dashboard(entries, session, query=""):
    total = len(entries)
    high = sum(entry["priority"] == 0 for entry in entries)
    green = sum(entry["result"]["decision"]["readiness"] == "green" for entry in entries)
    filtered = [entry for entry in entries if not query or query.casefold() in (str(entry["id"]) + " " + str(entry["inputs"].get("location", "")) + " " + str(entry["inputs"].get("notes", ""))).casefold()]
    content = '<div class="page-top"><span class="eyebrow">DEIN VERTRIEBSCOCKPIT</span><h1>Die nächste gute<br><em>Verbindung beginnt hier.</em></h1><p>Alle abgeschickten Checks, nach Vertriebspotenzial geordnet.</p></div><section class="stats"><article><span>Eingegangene Checks</span><strong>' + str(total) + '</strong></article><article><span>Hohe Priorität · A</span><strong>' + str(high) + '</strong></article><article><span>Technisch geeignet</span><strong>' + str(green) + '</strong></article></section>'
    content += '<section class="panel"><div class="table-top"><h2>Deine Einträge</h2><form action="/sales" method="get" class="search"><label class="sr-only" for="q">Einträge suchen</label><input id="q" name="q" placeholder="Region, Nummer oder Hinweis suchen" maxlength="200" value="' + escape(query, quote=True) + '"><button class="button secondary">Suchen</button></form></div>'
    if not filtered:
        content += '<div class="empty"><span>⌂</span><h2>' + ('Keine passenden Einträge.' if total else 'Noch keine Checks eingegangen.') + '</h2><p>Neue Berechnungen erscheinen hier automatisch. Erfasst wird ab Aktivierung der Vertriebsübersicht.</p><a class="button primary" href="/">Wärmepumpen-Check öffnen →</a></div>'
    else:
        content += '<div class="table-scroll"><table><thead><tr><th>Rang</th><th>Eintrag / Region</th><th>Priorität</th><th>Gebäude</th><th>Ersparnis / Jahr</th><th>Amortisation</th><th></th></tr></thead><tbody>'
        for rank, entry in enumerate(entries, 1):
            if entry not in filtered:
                continue
            code, label = PRIORITIES[entry["priority"]]
            location = escape(str(entry["inputs"].get("location") or "Region unbekannt"))
            created = datetime.fromisoformat(entry["created"]).strftime("%d.%m.%Y %H:%M UTC")
            savings, payback = metric(entry["result"], "annual_savings"), metric(entry["result"], "payback_period")
            action = '<a href="/sales/entry/' + str(entry["id"]) + '" class="detail-link">Details ↗</a>'
            if missing_requests(entry):
                action += '<form action="/sales/entry/' + str(entry["id"]) + '/reminder" method="post" class="reminder-short"><input type="hidden" name="csrf" value="' + escape(session["csrf"], quote=True) + '"><input type="hidden" name="request_key" value="' + secrets.token_urlsafe(24) + '"><input type="hidden" name="recipient" value="' + escape(entry["inputs"].get("contact_email", ""), quote=True) + '"><button class="button secondary">Daten per E-Mail anfragen</button><small>Lokale E-Mail-Demo</small></form>'
            content += '<tr><td class="rank">' + str(rank).zfill(2) + '</td><td><b>#' + str(entry["id"]).zfill(5) + ' · ' + location + '</b><small>' + created + '</small></td><td><span class="priority p' + str(entry["priority"]) + '">' + code + ' · ' + label + '</span><small>' + escape(entry["reason"]) + '</small></td><td>' + escape(text(entry["inputs"].get("floor_area_m2"))) + ' m²<small>' + escape(text(entry["inputs"].get("energy_carrier"))) + '</small></td><td>' + (escape(text(savings)) + ' €' if savings is not None else 'Noch offen') + '</td><td>' + (escape(text(payback)) + ' Jahre' if payback is not None else 'Noch offen') + '</td><td>' + action + '</td></tr>'
        content += '</tbody></table></div>'
    content += '</section><details class="ranking"><summary>So entsteht die Reihenfolge</summary><p>A: technisch geeignet und wirtschaftlich positiv. B: technisch geeignet, Wirtschaftlichkeit offen. C: technische Klärung erforderlich. D: widersprüchliche Angaben, unzureichende technische Belege oder negative Wirtschaftlichkeit.</p><p>Innerhalb jeder Gruppe: höhere verfügbare Jahresersparnis, dann kürzere verfügbare Amortisation, dann neuester Eingang. Fehlende Werte werden nicht als Null interpretiert. Das Ranking ändert keine Berechnung und ist keine Abschlusswahrscheinlichkeit.</p></details><p class="fine">Gespeichert werden Angaben und Ergebnisse ab Aktivierung dieser Funktion. Upload-Dateien werden nicht gespeichert. Zum Aktualisieren diese Seite neu laden.</p>'
    return page("Vertriebsübersicht", content, session)


def detail_page(entry, session, error=""):
    code, label = PRIORITIES[entry["priority"]]
    content = '<a class="detail-link" href="/sales">← Alle Einträge</a><div class="page-top"><span class="eyebrow">EINTRAG #' + str(entry["id"]).zfill(5) + '</span><h1>' + escape(str(entry["inputs"].get("location") or "Region unbekannt")) + '</h1><span class="priority p' + str(entry["priority"]) + '">' + code + ' · ' + label + '</span><p>' + escape(entry["reason"]) + '</p></div><section class="panel detail"><h2>Angaben zum Gebäude</h2><dl>'
    for key, value in entry["inputs"].items():
        content += '<dt>' + escape(LABELS.get(key, key)) + '</dt><dd>' + escape(text(value)) + '</dd>'
    content += '</dl></section><section class="panel detail"><h2>Bestehende Einschätzung</h2><p>' + escape(entry["result"]["decision"]["summary"]) + '</p><ul>'
    decision = entry["result"]["decision"]
    for reason in [*decision.get("reasons", []), *decision.get("validation_issues", [])]:
        content += '<li>' + escape(reason) + '</li>'
    content += '</ul></section>'
    missing = missing_requests(entry)
    if missing:
        content += '<section class="panel detail"><span class="eyebrow">NÄCHSTER KONTAKT</span><h2>Fehlende Angaben freundlich nachfragen</h2><p>Die Nachricht nennt automatisch diese offenen Angaben:</p><ul>' + ''.join('<li>' + escape(item) + '</li>' for item in missing) + '</ul><form action="/sales/entry/' + str(entry["id"]) + '/reminder" method="post"><input type="hidden" name="csrf" value="' + escape(session["csrf"], quote=True) + '"><input type="hidden" name="request_key" value="' + secrets.token_urlsafe(24) + '"><label>Kunden-E-Mail<input type="email" name="recipient" maxlength="254" autocomplete="email" required placeholder="kunde@beispiel.de" value="' + escape(entry["inputs"].get("contact_email", ""), quote=True) + '"></label>'
        if error:
            content += '<p role="alert" class="error">' + escape(error) + '</p>'
        content += '<button class="button primary">Daten per E-Mail anfragen →</button><p class="fine">Demo-Modus: Erstellt eine E-Mail im lokalen Postausgang. Es wird keine echte E-Mail versendet.</p></form></section>'
    content += '<section class="panel detail"><h2>Kennzahlen und Grundlagen</h2>'
    for key, item in entry["result"]["metrics"].items():
        if not item:
            continue
        value = text(item.get("value")) + " " + (item.get("unit") or "") if item.get("status") == "available" else "Noch offen (" + item.get("status", "unbekannt") + ")"
        content += '<details class="metric"><summary>' + escape(key) + '<b>' + escape(value) + '</b></summary>'
        for part in [*item.get("assumptions", []), *item.get("evidence", []), item.get("uncertainty"), item.get("source")]:
            if part:
                content += '<p>' + escape(str(part)) + '</p>'
        content += '</details>'
    return page("Eintrag #" + str(entry["id"]), content + '</section>', session)


def outbox_page(messages, session, focus_id=None):
    content = '<a class="detail-link" href="/sales">← Vertriebsübersicht</a><div class="page-top"><span class="eyebrow">LOKALER DEMO-POSTAUSGANG</span><h1>Freundlich nachgefragt.</h1><p>Diese Nachrichten sind lokal vorbereitet. Es wurde keine echte E-Mail versendet.</p></div>'
    if focus_id:
        content += '<p role="status" class="notice">Demo-E-Mail erstellt und im lokalen Postausgang abgelegt. Kein echter Versand.</p>'
    if not messages:
        content += '<section class="panel empty"><h2>Noch keine Demo-E-Mails.</h2><p>Bei unvollständigen Einträgen kannst du die fehlenden Angaben per Button anfragen.</p></section>'
    for message in messages:
        content += '<article class="panel detail"><span class="eyebrow">DEMO · NICHT VERSENDET</span><h2>' + escape(message["subject"]) + '</h2><p><b>An:</b> ' + escape(message["recipient"]) + '<br><b>Eintrag:</b> <a href="/sales/entry/' + str(message["entry_id"]) + '">#' + str(message["entry_id"]).zfill(5) + '</a><br><b>Erstellt:</b> ' + escape(message["created"]) + '</p><pre class="mail-body">' + escape(message["body"]) + '</pre></article>'
    return page("Demo-Postausgang", content, session)


SALES_CSS = """
:root{--ink:#203c34;--green:#254f40;--muted:#718070;--line:#e1e7db}*{box-sizing:border-box}body{margin:0;background:#f6f7f1;color:var(--ink);font:14px/1.6 'Segoe UI',Arial,sans-serif}a{color:inherit}header{padding:22px 5%;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--line);background:#fff}.brand{text-decoration:none;color:var(--green);font-size:25px;font-weight:700;letter-spacing:-1px}.brand span{font-size:21px;margin-left:9px}nav{display:flex;gap:24px;align-items:center}nav>a{font-size:12px;text-decoration:none;color:var(--muted)}main{max-width:1380px;margin:auto;padding:40px 5% 20px}h1{font-size:clamp(32px,4vw,49px);line-height:1.15;letter-spacing:-1.7px;font-weight:550;margin:16px 0 18px}h1 em{font-style:normal;color:#71905b}h2{font-size:19px;letter-spacing:-.5px;font-weight:600}.eyebrow{font-size:10px;letter-spacing:1.8px;font-weight:700;color:#7c9370}p{color:var(--muted)}.button{display:inline-flex;align-items:center;justify-content:space-between;gap:20px;border:1px solid #d8e2cc;border-radius:8px;padding:11px 17px;font:600 12px 'Segoe UI',sans-serif;text-decoration:none;cursor:pointer;white-space:nowrap}.primary{background:var(--green);color:white;border-color:var(--green)}.secondary{background:#fff;color:#668153}input{display:block;width:100%;min-height:45px;border:1px solid #dce4d3;border-radius:8px;padding:11px 12px;background:#fff;color:var(--ink);font:14px 'Segoe UI',sans-serif}input:focus{outline:2px solid #b1c796;outline-offset:2px}button:focus-visible,a:focus-visible{outline:3px solid #a7bd86;outline-offset:3px}label{display:block;font-size:12px;font-weight:600;color:#607453;margin:20px 0}label input{margin-top:7px}.login{max-width:480px;margin:20px auto 60px;padding:37px;border:1px solid var(--line);background:#fff;border-radius:20px;box-shadow:0 18px 60px #213b3510}.login h1{font-size:39px}.login .primary{width:100%;margin:8px 0}.login p{font-size:13px}.error{color:#a63f31!important;font-size:12px}.fine{font-size:11px!important;color:#819175}.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:30px 0}.stats article{border:1px solid var(--line);border-radius:14px;background:#fff;padding:22px}.stats article:first-child{background:var(--green);color:#fff;border-color:var(--green)}.stats span{font-size:12px;opacity:.8}.stats strong{display:block;font-size:34px;font-weight:550;letter-spacing:-1px;margin-top:5px}.panel{background:#fff;border:1px solid var(--line);border-radius:16px;overflow:hidden;margin-bottom:20px}.table-top{display:flex;justify-content:space-between;align-items:center;gap:20px;padding:20px 24px}.table-top h2{margin:0}.search{display:flex;gap:8px;max-width:440px;width:60%}.search input{font-size:12px;min-height:40px}.table-scroll{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:12px;text-align:left;min-width:900px}thead{background:#f7f9f3;color:#839575}th{font-size:10px;font-weight:650;padding:13px 18px;border-block:1px solid #e8ecdf}td{padding:20px 18px;border-bottom:1px solid #edf0e8;vertical-align:top}td b{font-weight:600}small{display:block;color:#86977b;font-size:10px;margin-top:6px;max-width:230px}.rank{font-size:19px;color:#8c9e7f}.priority{display:inline-block;padding:5px 10px;border-radius:20px;font-size:10px;background:#eef2e7;white-space:nowrap}.p0{background:#e2efd6;color:#466b31}.p1{background:#eef3df;color:#71823c}.p2{background:#fff3d9;color:#9d781f}.p3{background:#f8e9e2;color:#9c6150}.detail-link{font-size:12px;color:#547e42;text-decoration:none;white-space:nowrap}.empty{text-align:center;padding:45px 20px 65px}.empty>span{font-size:50px;color:#9eb48a}.empty p{font-size:12px;max-width:440px;margin:0 auto 25px}.ranking{padding:20px 0;font-size:12px;color:#72856a}.ranking summary{cursor:pointer;font-weight:600}.detail{padding:26px}.detail dl{display:grid;grid-template-columns:1fr 2fr;gap:10px 25px;font-size:13px}.detail dt{color:#819475}.detail dd{margin:0;white-space:pre-wrap;overflow-wrap:anywhere}.detail li{color:#708564;font-size:13px}.metric{border-top:1px solid #e5ebde;padding:14px 0;font-size:12px}.metric summary{display:flex;justify-content:space-between;gap:20px;cursor:pointer}.metric summary b{font-weight:600}.metric p{overflow-wrap:anywhere}.sr-only{position:absolute;width:1px;height:1px;padding:0;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}footer{padding:28px 5%;font-size:10px;color:#8a9a7d;max-width:1380px;margin:auto}@media(max-width:650px){header{padding:16px 5%;gap:10px}.brand{font-size:19px}.brand span{font-size:17px}nav{gap:10px}nav>a{font-size:10px}.button{font-size:11px;padding:10px 12px;gap:10px}main{padding-top:25px}.login{padding:25px;margin-top:5px}.login h1{font-size:33px}.stats{gap:9px}.stats article{padding:14px}.stats span{font-size:10px}.stats strong{font-size:28px}.table-top{align-items:stretch;flex-direction:column;padding:20px}.search{width:100%;max-width:none}.detail{padding:20px}.detail dl{grid-template-columns:1fr}.detail dd{margin-bottom:10px}.metric summary{flex-direction:column;gap:4px}}
""".encode()
SALES_CSS += b".reminder-short{margin-top:10px}.reminder-short .button{font-size:10px;padding:8px 10px}.mail-body{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.9 'Segoe UI',Arial,sans-serif;color:#536c49}.notice{background:#e6efd9;border:1px solid #d1dfbf;padding:16px;border-radius:10px;color:#4f6e3b}nav{flex-wrap:wrap}"
