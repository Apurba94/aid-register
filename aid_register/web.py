"""The offline web app."""
import json
from datetime import datetime

from . import core
from .fieldkit import App, Fail, Raw, bar_chart, card, download, form, h, link, redirect, stats, table

SCHEMA = """
CREATE TABLE IF NOT EXISTS households (id INTEGER PRIMARY KEY, head TEXT NOT NULL, members INTEGER NOT NULL CHECK (members > 0), phone TEXT NOT NULL DEFAULT '', block TEXT NOT NULL DEFAULT '', birth_year INTEGER NOT NULL DEFAULT 0, father TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'active');
CREATE TABLE IF NOT EXISTS rounds (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, ration TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS collections (round INTEGER NOT NULL REFERENCES rounds(id), household INTEGER NOT NULL REFERENCES households(id), at TEXT NOT NULL, staff TEXT NOT NULL DEFAULT '', PRIMARY KEY (round, household));
CREATE TABLE IF NOT EXISTS reviewed (a INTEGER NOT NULL, b INTEGER NOT NULL, verdict TEXT NOT NULL, PRIMARY KEY (a, b));
"""


def create_app(db="aid.db", clock=datetime.now):
    a = App("Aid Register", db, SCHEMA, [("Overview", "/"), ("Households", "/households"), ("Rounds", "/rounds"), ("Possible duplicates", "/duplicates")])

    def to_h(r):
        return core.Household(r["id"], r["head"], r["members"], r["phone"], r["block"], r["birth_year"], r["father"])

    def active():
        return a.rows("SELECT * FROM households WHERE status = 'active' ORDER BY id")

    @a.route("/")
    def home(req):
        rounds = a.rows("SELECT r.id, r.name, COUNT(c.household) done FROM rounds r LEFT JOIN collections c ON c.round = r.id GROUP BY r.id ORDER BY r.id DESC")
        hs = active()
        total = len(hs)
        return a.page("Overview", stats([("Households", total), ("People", sum(h["members"] for h in hs)), ("Rounds", len(rounds))]) + card("Distribution rounds", table(rounds, [("Round", lambda r: link(f"/round/{r['id']}", r["name"])), ("Collected", lambda r: f"{r['done']} of {total}"), ("Coverage", lambda r: f"{r['done'] / total:.0%}" if total else "")], "No rounds yet.")))

    @a.route("/households", ("GET", "POST"))
    def households(req):
        if req.method == "POST":
            a.run("INSERT INTO households (head, members, phone, block, birth_year, father) VALUES (?, ?, ?, ?, ?, ?)", req.text("head"), int(req.number("members", low=1, high=60)), req.text("phone", False), req.text("block", False), int(req.number("birth_year", 0, 0, 2100)), req.text("father", False))
            a.log("register household", req.text("head"))
            return redirect("/households")
        q = req.get("q").strip().lower()
        rows = [r for r in a.rows("SELECT * FROM households ORDER BY id DESC LIMIT 5000") if not q or q in r["head"].lower() or q == str(r["id"]) or q in r["phone"]][:200]
        return a.page("Households", card("Register a household", form(a, "/households", [("head", "Head of household"), ("members", "Members", "number", 1), ("father", "Father's name"), ("birth_year", "Birth year", "number", 0), ("phone", "Phone"), ("block", "Block")], "Register")) + card("Search", f'<form method="get" action="/households"><label>Name, number or phone<input name="q" value="{h(q)}"></label><button>Search</button></form>') + card("Households", table(rows, [("No.", "id"), ("Head", "head"), ("Members", "members"), ("Block", "block"), ("Status", "status")], "No households found.")))

    @a.route("/rounds", ("GET", "POST"))
    def rounds(req):
        if req.method == "POST":
            ration = []
            for line in req.text("ration").splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) < 3:
                    raise Fail("Each ration line needs: item, base, per person, and an optional cap")
                try:
                    ration.append([parts[0], float(parts[1]), float(parts[2]), float(parts[3]) if len(parts) > 3 and parts[3] else None])
                except ValueError:
                    raise Fail(f"Numbers are needed in: {line}") from None
            cur = a.run("INSERT INTO rounds (name, ration) VALUES (?, ?)", req.text("name"), json.dumps(ration, ensure_ascii=False))
            return redirect(f"/round/{cur.lastrowid}")
        return a.page("New round", card("One item per line: item, base, per person, cap", form(a, "/rounds", [("name", "Round name"), ("ration", "Ration", "textarea", "Rice kg, 0, 6, 40\nOil litres, 1, 0.25, 3")], "Create")))

    @a.route("/round/<id>", ("GET", "POST"))
    def round_page(req, id):
        r = a.row("SELECT * FROM rounds WHERE id = ?", id)
        if r is None:
            raise Fail("No such round", 404)
        ration = json.loads(r["ration"])
        if req.method == "POST":
            hh = int(req.number("household", low=1))
            row = a.row("SELECT * FROM households WHERE id = ?", hh)
            if row is None or row["status"] != "active":
                raise Fail(f"Household {hh} is not active on the register", 404)
            done = a.row("SELECT at FROM collections WHERE round = ? AND household = ?", id, hh)
            if done:
                raise Fail(f"Household {hh} already collected in this round, at {done['at']}. Do not hand over again without a supervisor.", 409)
            a.run("INSERT INTO collections (round, household, at, staff) VALUES (?, ?, ?, ?)", id, hh, clock().isoformat(timespec="minutes"), req.text("staff", False))
            return redirect(f"/round/{id}?last={hh}")
        hs = [to_h(x) for x in active()]
        need = core.round_totals(hs, ration)
        done = {c["household"] for c in a.rows("SELECT household FROM collections WHERE round = ?", id)}
        given = core.round_totals([x for x in hs if x.id in done], ration)
        note = ""
        last = req.get("last")
        if last:
            row = a.row("SELECT * FROM households WHERE id = ?", last)
            if row:
                ent = core.entitlement(row["members"], ration)
                note = f"Household {row['id']}, {row['members']} members: give " + ", ".join(f"{q:g} {item}" for item, q in ent.items())
        body = stats([("Collected", f"{len(done)} of {len(hs)}"), ("Coverage", f"{len(done) / len(hs):.0%}" if hs else "n/a")])
        body += card("Record a collection", form(a, f"/round/{id}", [("household", "Household number", "number"), ("staff", "Staff")], "Record"))
        body += card("Stock", table([{"i": k, "n": v, "g": given.get(k, 0)} for k, v in need.items()], [("Item", "i"), ("Needed", lambda x: f"{x['n']:g}"), ("Given", lambda x: f"{x['g']:g}")]))
        body += f'<p><a href="/round/{id}/missing.csv">Download who has not collected</a></p>'
        return a.page(r["name"], body, note)

    @a.route("/round/<id>/missing.csv")
    def missing(req, id):
        rows = a.rows("SELECT id, head, block, members FROM households h WHERE status = 'active' AND NOT EXISTS (SELECT 1 FROM collections c WHERE c.round = ? AND c.household = h.id) ORDER BY block, id", id)
        return download(rows, ["id", "head", "block", "members"], "not-collected.csv")

    @a.route("/duplicates", ("GET", "POST"))
    def duplicates(req):
        if req.method == "POST":
            x, y = sorted((int(req.number("a")), int(req.number("b"))))
            verdict = req.text("verdict")
            if verdict not in ("different", "same"):
                raise Fail("Unknown choice")
            a.run("INSERT OR REPLACE INTO reviewed (a, b, verdict) VALUES (?, ?, ?)", x, y, verdict)
            if verdict == "same":
                a.run("UPDATE households SET status = 'merged' WHERE id = ?", y)
            a.log("duplicate review", f"{x} {y} {verdict}")
            return redirect("/duplicates")
        done = {(r["a"], r["b"]) for r in a.rows("SELECT a, b FROM reviewed")}
        pairs = [p for p in core.find_duplicates([to_h(x) for x in active()]) if (p[1], p[2]) not in done][:100]
        names = {r["id"]: r for r in a.rows("SELECT * FROM households")}

        def actions(p):
            f = lambda v, t: f'<form method="post" action="/duplicates" style="display:inline-block;margin:2px">{a.form_token()}<input type="hidden" name="a" value="{p[1]}"><input type="hidden" name="b" value="{p[2]}"><input type="hidden" name="verdict" value="{v}"><button>{t}</button></form>'
            return Raw(f("different", "Different people") + f("same", "Same household"))
        return a.page("Possible duplicates", card("Check each pair with the people concerned before deciding", table(pairs, [("Score", lambda p: f"{p[0]:.0%}"), ("First", lambda p: f"{p[1]}: {names[p[1]]['head']} ({names[p[1]]['members']})"), ("Second", lambda p: f"{p[2]}: {names[p[2]]['head']} ({names[p[2]]['members']})"), ("Why", lambda p: "; ".join(p[3])), ("Decision", actions)], "No possible duplicates to review.")))

    return a
