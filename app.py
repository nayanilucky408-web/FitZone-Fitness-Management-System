from flask import Flask, request, redirect, url_for, render_template_string, flash
import sqlite3
from pathlib import Path
from datetime import date, timedelta

app = Flask(__name__)
app.secret_key = "fitzone-student-project-key"

DB_PATH = Path(__file__).with_name("gym.db")

# Default prices can be changed here.
PLAN_DETAILS = {
    "Monthly": {"months": 1, "fee": 1000},
    "Quarterly": {"months": 3, "fee": 2700},
    "Half-Yearly": {"months": 6, "fee": 5000},
    "Yearly": {"months": 12, "fee": 9000},
}
ALLOWED_PLANS = list(PLAN_DETAILS.keys())


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def add_column_if_missing(conn, table, column, definition):
    existing = {
        row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def calculate_expiry(start_date, plan):
    """Return the expiry date by adding the plan duration to the start date."""
    start = date.fromisoformat(start_date)
    months = PLAN_DETAILS[plan]["months"]
    # Add calendar months without requiring an extra package.
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    import calendar
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day).isoformat()


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                email TEXT,
                plan TEXT NOT NULL,
                join_date TEXT NOT NULL
            )
        """)
       
        conn.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                member_id INTEGER NOT NULL,
                amount INTEGER NOT NULL CHECK (amount > 0),
                payment_date TEXT NOT NULL,
                payment_method TEXT NOT NULL DEFAULT 'Cash',
                notes TEXT,
                FOREIGN KEY (member_id) REFERENCES members(id)
            )
        """) 

        # Safely upgrade an existing database; existing member rows are preserved.
        add_column_if_missing(conn, "members", "membership_start", "TEXT")
        add_column_if_missing(conn, "members", "expiry_date", "TEXT")
        add_column_if_missing(conn, "members", "fee", "INTEGER NOT NULL DEFAULT 0")
        add_column_if_missing(conn, "members", "amount_paid", "INTEGER NOT NULL DEFAULT 0")

        rows = conn.execute(
            "SELECT id, plan, join_date, membership_start, expiry_date, fee "
            "FROM members"
        ).fetchall()
        for row in rows:
            plan = row["plan"] if row["plan"] in PLAN_DETAILS else "Monthly"
            start = row["membership_start"] or row["join_date"] or date.today().isoformat()
            expiry = row["expiry_date"] or calculate_expiry(start, plan)
            fee = row["fee"] or PLAN_DETAILS[plan]["fee"]
            conn.execute("""
                UPDATE members
                SET membership_start = ?, expiry_date = ?, fee = ?
                WHERE id = ?
            """, (start, expiry, fee, row["id"]))


init_db()

PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FitZone | Gym Management</title>

<style>
* {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}

:root {
    --bg: #0b0f19;
    --panel: #141b2a;
    --panel-hover: #1b2638;
    --border: #29364b;
    --text: #f3f6fc;
    --muted: #9aa8bd;
    --accent: #b8ff3b;
    --accent-soft: rgba(184, 255, 59, 0.10);
}

body {
    font-family: "Segoe UI", Arial, sans-serif;
    background:
        radial-gradient(ellipse at top right, #19253a 0%, transparent 45%),
        var(--bg);
    color: var(--text);
    line-height: 1.6;
}

.layout {
    display: flex;
    min-height: 100vh;
}

.sidebar {
    width: 245px;
    background: rgba(16, 23, 36, 0.96);
    border-right: 1px solid var(--border);
    padding: 30px 18px;
    flex-shrink: 0;
}

.logo {
    color: var(--accent);
    font-size: 27px;
    font-weight: 900;
    letter-spacing: 1px;
    margin-bottom: 42px;
    text-shadow: 0 0 20px rgba(184, 255, 59, 0.15);
}

.nav a {
    display: block;
    color: var(--muted);
    text-decoration: none;
    padding: 13px 15px;
    margin-bottom: 9px;
    border: 1px solid transparent;
    border-radius: 10px;
    transition: 0.2s ease;
}

.nav a:hover {
    color: var(--text);
    background: var(--panel-hover);
    border-color: var(--border);
    transform: translateX(3px);
}

.nav a.active {
    background: var(--accent);
    color: #11170a;
    font-weight: 700;
    box-shadow: 0 5px 20px rgba(184, 255, 59, 0.12);
}

main {
    flex: 1;
    min-width: 0;
    padding: 34px;
}

.topbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 18px;
    flex-wrap: wrap;
    margin-bottom: 32px;
}

h1 {
    font-size: clamp(26px, 3vw, 35px);
    line-height: 1.25;
    margin-bottom: 8px;
    letter-spacing: -0.8px;
}

h2 {
    line-height: 1.35;
}

.muted {
    color: var(--muted);
}

.admin {
    background: var(--panel);
    border: 1px solid var(--border);
    padding: 12px 18px;
    border-radius: 11px;
    color: var(--text);
}

.cards {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 20px;
    margin-bottom: 28px;
}

.card,
.section {
    background: linear-gradient(145deg, #172033, #121927);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 25px;
    margin-bottom: 23px;
    box-shadow: 0 12px 30px rgba(0, 0, 0, 0.12);
    transition: border-color 0.2s, transform 0.2s;
}

.card:hover {
    border-color: #465b3b;
    transform: translateY(-2px);
}

.card p {
    color: var(--muted);
    margin-bottom: 13px;
}

.card h2 {
    color: var(--accent);
    font-size: 32px;
    font-weight: 800;
}

.section h2 {
    margin-bottom: 18px;
}

button,
.button {
    display: inline-block;
    border: 1px solid transparent;
    border-radius: 9px;
    padding: 12px 17px;
    background: var(--accent);
    color: #11170a;
    font-weight: 750;
    cursor: pointer;
    text-decoration: none;
    font-family: inherit;
    font-size: 14px;
    transition: 0.2s ease;
}

button:hover,
.button:hover {
    background: #d0ff83;
    transform: translateY(-1px);
    box-shadow: 0 5px 18px rgba(184, 255, 59, 0.12);
}

.secondary {
    background: #29354a;
    color: var(--text);
    border-color: #39465c;
}

.secondary:hover {
    background: #39465c;
}

.danger {
    background: #572b37;
    color: #ffdce2;
    border-color: #75404d;
}

.danger:hover {
    background: #713344;
}

input,
select {
    width: 100%;
    background: #0c1320;
    color: var(--text);
    border: 1px solid #35435a;
    padding: 13px 14px;
    border-radius: 9px;
    margin-top: 8px;
    margin-bottom: 17px;
    font: inherit;
    outline: none;
    transition: border-color 0.2s, box-shadow 0.2s;
}

input:focus,
select:focus {
    border-color: var(--accent);
    box-shadow: 0 0 0 3px rgba(184, 255, 59, 0.10);
}

label {
    color: #dce5f2;
    font-size: 14px;
    font-weight: 600;
}

.form-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px 18px;
}

.form-actions {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
}

.search-row {
    display: flex;
    gap: 10px;
    align-items: center;
    flex-wrap: wrap;
    margin-bottom: 20px;
}

.search-row input {
    flex: 1;
    min-width: 180px;
    margin: 0;
}

.table-wrap {
    width: 100%;
    overflow-x: auto;
    border-radius: 10px;
}

table {
    border-collapse: collapse;
    width: 100%;
    min-width: 760px;
}

th,
td {
    padding: 15px 12px;
    text-align: left;
    border-bottom: 1px solid #2b374a;
    font-size: 14px;
}

th {
    color: var(--accent);
    background: #202b3e;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    white-space: nowrap;
}

td {
    color: #dce5f2;
}

tbody tr:hover,
tr:hover td {
    background-color: rgba(184, 255, 59, 0.035);
}

.actions {
    display: flex;
    gap: 7px;
    align-items: center;
    flex-wrap: wrap;
}

.actions form {
    display: inline;
}

.actions button {
    padding: 8px 11px;
}

.notice {
    background: #1c3025;
    color: #d7ffbb;
    border: 1px solid #365d3c;
    padding: 14px 17px;
    border-radius: 10px;
    margin-bottom: 20px;
}

.empty {
    padding: 24px 0;
    color: var(--muted);
}

.pill {
    display: inline-block;
    border-radius: 20px;
    padding: 5px 11px;
    font-size: 12px;
    background: #29354a;
    border: 1px solid #3b4960;
}

.good {
    color: var(--accent);
}

.bad {
    color: #ff9caa;
}

footer {
    color: #77869d;
    font-size: 12px;
    margin-top: 28px;
}

@media (max-width: 1000px) {
    .sidebar {
        width: 215px;
    }

    main {
        padding: 23px;
    }

    .cards {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
}

@media (max-width: 700px) {
    .layout {
        flex-direction: column;
    }

    .sidebar {
        width: 100%;
        padding: 20px 16px;
    }

    .logo {
        margin-bottom: 18px;
    }

    .nav {
        display: flex;
        flex-wrap: wrap;
        gap: 5px;
    }

    .nav a {
        padding: 10px 12px;
        margin: 0;
    }

    main {
        padding: 18px 14px;
    }

    .cards,
    .form-grid {
        grid-template-columns: 1fr;
    }

    .card,
    .section {
        padding: 18px;
    }
}
</style>
</head>
<body>
<div class="layout">
<aside class="sidebar">
    <div class="logo">FITZONE.</div>
  
<nav class="nav">
    <a class="{{ 'active' if page == 'dashboard' else '' }}" href="{{ url_for('dashboard') }}">Dashboard</a>
    <a class="{{ 'active' if page in ['members','edit','add'] else '' }}" href="{{ url_for('members') }}">Members</a>
    <a class="{{ 'active' if page == 'memberships' else '' }}" href="{{ url_for('memberships') }}">Memberships</a>
    <a href="{{ url_for('attendance') }}">Attendance</a>
    <a href="{{ url_for('payments') }}">Payments</a>
</nav>
</aside>
<main>
    <div class="topbar">
        <div><h1>{{ heading }}</h1><p class="muted">Fitness and Gym Management System</p></div>
        <div class="admin">Administrator</div>
    </div>
    {% for message in get_flashed_messages() %}<div class="notice">{{ message }}</div>{% endfor %}

    {% if page == 'dashboard' %}
        <div class="cards">
            <div class="card"><p>Total Registered Members</p><h2>{{ total }}</h2></div>
            <div class="card"><p>Membership Plans Used</p><h2>{{ plans }}</h2></div>
            <div class="card"><p>Expired Memberships</p><h2>{{ expired_count }}</h2></div>
        </div>
        <section class="section">
            <h2>Member Management</h2>
            <p class="muted">Register members, update their plans, and track expiry dates and fee balances.</p><br>
            <a class="button" href="{{ url_for('members') }}">Manage Members</a>
            <a class="button secondary" href="{{ url_for('add_member') }}">+ Add Member</a>
            <a class="button secondary" href="{{ url_for('memberships') }}">View Memberships</a>
        </section>
        <section class="section">
            <h2>Recent Members</h2>
            {% if recent %}
            <div class="table-wrap"><table>
                <tr><th>Name</th><th>Plan</th><th>Start Date</th><th>Expiry Date</th><th>Fee</th><th>Balance</th></tr>
                {% for m in recent %}
                <tr><td>{{ m.name }}</td><td>{{ m.plan }}</td><td>{{ m.membership_start }}</td><td>{{ m.expiry_date }}</td><td>₹{{ m.fee }}</td><td>₹{{ m.fee - m.amount_paid }}</td></tr>
                {% endfor %}
            </table></div>
            {% else %}<p class="empty">No members registered yet. Add your first member!</p>{% endif %}
        </section>

    {% elif page in ['members','edit','add'] %}
        <section class="section">
            <h2>{{ 'Edit Member and Membership' if page == 'edit' else 'Register a New Member' }}</h2>
            <form method="post" action="{{ url_for('edit_member', member_id=member.id) if page == 'edit' else url_for('add_member') }}">
                <div class="form-grid">
                    <div><label>Full Name *</label><input name="name" required maxlength="100" placeholder="Enter full name" value="{{ member.name if member else '' }}"></div>
                    <div><label>Phone Number *</label><input name="phone" required maxlength="20" placeholder="Enter phone number" value="{{ member.phone if member else '' }}"></div>
                    <div><label>Email Address</label><input type="email" name="email" maxlength="120" placeholder="Enter email" value="{{ member.email if member else '' }}"></div>
                    <div><label>Membership Plan *</label>
                        <select name="plan" id="plan" required>
                            {% for p in plan_details %}
                            <option value="{{ p }}" {% if member and member.plan == p %}selected{% endif %}>{{ p }} — ₹{{ plan_details[p].fee }}</option>
                            {% endfor %}
                        </select>
                    </div>
                    <div><label>Membership Start Date *</label><input type="date" name="membership_start" id="membership_start" required value="{{ member.membership_start if member else today }}"></div>
                    <div><label>Membership Fee (₹) *</label><input type="number" min="0" step="1" name="fee" id="fee" required value="{{ member.fee if member else plan_details['Monthly'].fee }}"></div>
                    <div><label>Amount Paid (₹) *</label><input type="number" min="0" step="1" name="amount_paid" required value="{{ member.amount_paid if member else 0 }}"></div>
                </div>
                <p class="muted" style="margin-bottom:16px">Expiry date is calculated automatically from the plan and start date. You can adjust the fee if your gym uses different prices.</p>
                <div class="form-actions"><button type="submit">{{ 'Save Changes' if page == 'edit' else 'Register Member' }}</button><a class="button secondary" href="{{ url_for('members') }}">Cancel</a></div>
            </form>
        </section>
        <section class="section">
            <h2>Member Directory</h2>
            <form class="search-row" method="get" action="{{ url_for('members') }}">
                <input name="q" value="{{ query }}" placeholder="Search by name, phone or email">
                <button type="submit">Search</button><a class="button secondary" href="{{ url_for('members') }}">Clear</a>
            </form>
            {% if all_members %}
            <div class="table-wrap"><table>
                <tr><th>ID</th><th>Name</th><th>Phone</th><th>Email</th><th>Plan</th><th>Expiry</th><th>Fee</th><th>Balance</th><th>Actions</th></tr>
                {% for m in all_members %}
                <tr>
                    <td>{{ m.id }}</td><td>{{ m.name }}</td><td>{{ m.phone }}</td><td>{{ m.email or '-' }}</td><td>{{ m.plan }}</td>
                    <td>{{ m.expiry_date }} {% if m.expiry_date < today %}<span class="pill bad">Expired</span>{% else %}<span class="pill good">Active</span>{% endif %}</td>
                    <td>₹{{ m.fee }}</td><td>₹{{ m.fee - m.amount_paid }}</td>
                    <td><div class="actions">
                        <a class="button secondary" href="{{ url_for('edit_member', member_id=m.id) }}">Edit</a>
                        <form method="post" action="{{ url_for('delete_member', member_id=m.id) }}" onsubmit="return confirm('Delete this member permanently?');"><button class="danger" type="submit">Delete</button></form>
                    </div></td>
                </tr>
                {% endfor %}
            </table></div>
            {% else %}<p class="empty">No matching members found.</p>{% endif %}
        </section>

    {% elif page == 'memberships' %}
        <section class="section">
            <h2>Membership Overview</h2>
            <p class="muted" style="margin-bottom:18px">Track each member's plan, dates, fee, amount paid, and remaining balance.</p>
            {% if all_members %}
            <div class="table-wrap"><table>
                <tr><th>Member</th><th>Plan</th><th>Start</th><th>Expiry</th><th>Membership</th><th>Fee</th><th>Paid</th><th>Balance</th><th>Payment Status</th><th>Action</th></tr>
                {% for m in all_members %}
                <tr>
                    <td>{{ m.name }}</td><td>{{ m.plan }}</td><td>{{ m.membership_start }}</td><td>{{ m.expiry_date }}</td>
                    <td>{% if m.expiry_date < today %}<span class="pill bad">Expired</span>{% else %}<span class="pill good">Active</span>{% endif %}</td>
                    <td>₹{{ m.fee }}</td><td>₹{{ m.amount_paid }}</td><td>₹{{ m.fee - m.amount_paid }}</td>
                    <td>{% if m.amount_paid >= m.fee %}<span class="pill good">Paid</span>{% elif m.amount_paid > 0 %}<span class="pill">Partial</span>{% else %}<span class="pill bad">Pending</span>{% endif %}</td>
                    <td><a class="button secondary" href="{{ url_for('edit_member', member_id=m.id) }}">Edit</a></td>
                </tr>
                {% endfor %}
            </table></div>
            {% else %}<p class="empty">No memberships yet. Register a member first.</p>{% endif %}
        </section>
    {% endif %}
    <footer>FITZONE | Student Project | Flask + SQLite</footer>
</main>
</div>
<script>
const planSelect = document.getElementById("plan");
const feeInput = document.getElementById("fee");
if (planSelect && feeInput) {
    const prices = { "Monthly": 1000, "Quarterly": 2700, "Half-Yearly": 5000, "Yearly": 9000 };
    planSelect.addEventListener("change", () => { feeInput.value = prices[planSelect.value] || 0; });
}
</script>
</body>
</html>
"""


def member_status(row):
    return "Expired" if row["expiry_date"] < date.today().isoformat() else "Active"


@app.route("/")
def dashboard():
    with get_db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM members").fetchone()[0]
        plans = conn.execute("SELECT COUNT(DISTINCT plan) FROM members").fetchone()[0]
        expired_count = conn.execute(
            "SELECT COUNT(*) FROM members WHERE expiry_date < ?", (date.today().isoformat(),)
        ).fetchone()[0]
        recent = conn.execute("SELECT * FROM members ORDER BY id DESC LIMIT 5").fetchall()
    return render_template_string(
        PAGE, page="dashboard", heading="Gym Dashboard", total=total, plans=plans,
        expired_count=expired_count, recent=recent, today=date.today().isoformat(),
        plan_details=PLAN_DETAILS
    )


@app.route("/members")
def members():
    query = request.args.get("q", "").strip()
    with get_db() as conn:
        if query:
            pattern = f"%{query}%"
            all_members = conn.execute("""
                SELECT * FROM members
                WHERE name LIKE ? OR phone LIKE ? OR email LIKE ?
                ORDER BY id DESC
            """, (pattern, pattern, pattern)).fetchall()
        else:
            all_members = conn.execute("SELECT * FROM members ORDER BY id DESC").fetchall()
    return render_template_string(
        PAGE, page="members", heading="Member Management", all_members=all_members,
        query=query, member=None, today=date.today().isoformat(), plan_details=PLAN_DETAILS
    )


@app.route("/members/add", methods=["GET", "POST"])
def add_member():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()
        plan = request.form.get("plan", "").strip()
        start = request.form.get("membership_start", date.today().isoformat())
        try:
            fee = int(request.form.get("fee", PLAN_DETAILS.get(plan, {}).get("fee", 0)))
            amount_paid = int(request.form.get("amount_paid", "0"))
            date.fromisoformat(start)
        except (ValueError, TypeError):
            flash("Please enter a valid date and whole-number fee amounts.")
            return redirect(url_for("members"))
        if not name or not phone or plan not in ALLOWED_PLANS or fee < 0 or amount_paid < 0 or amount_paid > fee:
            flash("Check the name, phone, plan, fee, and amount paid. Amount paid cannot exceed the fee.")
            return redirect(url_for("members"))
        expiry = calculate_expiry(start, plan)
        with get_db() as conn:
            conn.execute("""
                INSERT INTO members
                (name, phone, email, plan, join_date, membership_start, expiry_date, fee, amount_paid)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (name, phone, email, plan, start, start, expiry, fee, amount_paid))
        flash(f"Member {name} registered successfully. Membership expires on {expiry}.")
        return redirect(url_for("members"))
    return redirect(url_for("members"))


@app.route("/members/edit/<int:member_id>", methods=["GET", "POST"])
def edit_member(member_id):
    with get_db() as conn:
        member = conn.execute("SELECT * FROM members WHERE id = ?", (member_id,)).fetchone()
    if member is None:
        flash("Member not found.")
        return redirect(url_for("members"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()
        plan = request.form.get("plan", "").strip()
        start = request.form.get("membership_start", date.today().isoformat())
        try:
            fee = int(request.form.get("fee", "0"))
            amount_paid = int(request.form.get("amount_paid", "0"))
            date.fromisoformat(start)
        except (ValueError, TypeError):
            flash("Please enter a valid date and whole-number fee amounts.")
            return redirect(url_for("edit_member", member_id=member_id))
        if not name or not phone or plan not in ALLOWED_PLANS or fee < 0 or amount_paid < 0 or amount_paid > fee:
            flash("Check the name, phone, plan, fee, and amount paid. Amount paid cannot exceed the fee.")
            return redirect(url_for("edit_member", member_id=member_id))
        expiry = calculate_expiry(start, plan)
        with get_db() as conn:
            conn.execute("""
                UPDATE members
                SET name=?, phone=?, email=?, plan=?, membership_start=?, expiry_date=?,
                    fee=?, amount_paid=?
                WHERE id=?
            """, (name, phone, email, plan, start, expiry, fee, amount_paid, member_id))
        flash("Member and membership updated successfully.")
        return redirect(url_for("memberships"))

    with get_db() as conn:
        all_members = conn.execute("SELECT * FROM members ORDER BY id DESC").fetchall()
    return render_template_string(
        PAGE, page="edit", heading="Edit Member", member=member, all_members=all_members,
        query="", today=date.today().isoformat(), plan_details=PLAN_DETAILS
    )


@app.route("/members/delete/<int:member_id>", methods=["POST"])
def delete_member(member_id):
    with get_db() as conn:
        conn.execute("DELETE FROM members WHERE id = ?", (member_id,))
    flash("Member deleted successfully.")
    return redirect(url_for("members"))


@app.route("/memberships")
def memberships():
    with get_db() as conn:
        all_members = conn.execute("SELECT * FROM members ORDER BY expiry_date ASC").fetchall()
    return render_template_string(
        PAGE, page="memberships", heading="Membership Management", all_members=all_members,
        today=date.today().isoformat(), plan_details=PLAN_DETAILS
    )

@app.route("/payments", methods=["GET", "POST"])
def payments():
    with get_db() as conn:
        if request.method == "POST":
            member_id = request.form.get("member_id", type=int)
            amount = request.form.get("amount", type=int)
            payment_date = request.form.get("payment_date", "").strip()
            payment_method = request.form.get("payment_method", "Cash").strip()
            notes = request.form.get("notes", "").strip()

            if not member_id or not amount or amount <= 0 or not payment_date:
                flash("Enter a valid member, amount, and payment date.")
                return redirect(url_for("payments"))

            member = conn.execute(
                "SELECT id, name, fee, amount_paid FROM members WHERE id = ?",
                (member_id,)
            ).fetchone()

            if member is None:
                flash("Please select a valid member.")
                return redirect(url_for("payments"))

            if amount > int(member["fee"]) - int(member["amount_paid"]):
                flash("Payment exceeds the member's remaining balance.")
                return redirect(url_for("payments"))

            conn.execute("""
                INSERT INTO payments
                (member_id, amount, payment_date, payment_method, notes)
                VALUES (?, ?, ?, ?, ?)
            """, (member_id, amount, payment_date, payment_method, notes))

            conn.execute("""
                UPDATE members
                SET amount_paid = amount_paid + ?
                WHERE id = ?
            """, (amount, member_id))

            flash("Payment recorded successfully!")

            return redirect(url_for("payments"))

        members = conn.execute("""
            SELECT id, name, plan, fee, amount_paid
            FROM members
            ORDER BY name
        """).fetchall()

        history = conn.execute("""
            SELECT payments.id, members.name, payments.amount,
                   payments.payment_date, payments.payment_method,
                   payments.notes
            FROM payments
            JOIN members ON members.id = payments.member_id
            ORDER BY payments.id DESC
        """).fetchall()

        total = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM payments"
        ).fetchone()[0]

        return render_template_string("""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Payment History - FitZone</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body {
                    background: #10131c;
                    color: #f3f4f6;
                    font-family: Arial, sans-serif;
                    padding: 24px;
                }
                .card {
                    background: #1b2030;
                    padding: 20px;
                    margin-bottom: 22px;
                    border-radius: 12px;
                }
                input, select, textarea, button {
                    box-sizing: border-box;
                    width: 100%;
                    padding: 11px;
                    margin: 7px 0 14px;
                    border-radius: 6px;
                    border: 1px solid #454b60;
                }
                input, select, textarea {
                    background: #10131c;
                    color: white;
                }
                button {
                    background: #19c37d;
                    color: #10131c;
                    font-weight: bold;
                    cursor: pointer;
                }
                table {
                    width: 100%;
                    border-collapse: collapse;
                    min-width: 650px;
                }
                th, td {
                    padding: 12px;
                    text-align: left;
                    border-bottom: 1px solid #383e50;
                }
                .table-wrap {
                    overflow-x: auto;
                }
                a { color: #19c37d; }
                .message { color: #19c37d; }
            </style>
        </head>
        <body>
            <p><a href="/">← Back to Dashboard</a></p>
            <h1>Payment History</h1>

            {% with messages = get_flashed_messages() %}
                {% for message in messages %}
                    <p class="message">{{ message }}</p>
                {% endfor %}
            {% endwith %}

            <div class="card">
                <h2>Total Payments Recorded: ₹{{ total }}</h2>
            </div>

            <div class="card">
                <h2>Record a Payment</h2>
                <form method="POST">
                    <label>Member</label>
                    <select name="member_id" required>
                        <option value="">Select a member</option>
                        {% for m in members %}
                            <option value="{{ m.id }}">
                                {{ m.name }} — Balance ₹{{ m.fee - m.amount_paid }}
                            </option>
                        {% endfor %}
                    </select>

                    <label>Amount (₹)</label>
                    <input type="number" name="amount" min="1"
                           step="1" required>

                    <label>Payment Date</label>
                    <input type="date" name="payment_date"
                           value="{{ today }}" required>

                    <label>Payment Method</label>
                    <select name="payment_method" required>
                        <option>Cash</option>
                        <option>UPI</option>
                        <option>Card</option>
                        <option>Bank Transfer</option>
                    </select>

                    <label>Notes (optional)</label>
                    <textarea name="notes" rows="2"></textarea>

                    <button type="submit">Save Payment</button>
                </form>
            </div>

            <div class="card">
                <h2>Recent Payments</h2>
                <div class="table-wrap">
                    <table>
                        <tr>
                            <th>Member</th>
                            <th>Amount</th>
                            <th>Date</th>
                            <th>Method</th>
                            <th>Notes</th>
                        </tr>
                        {% for p in history %}
                        <tr>
                            <td>{{ p.name }}</td>
                            <td>₹{{ p.amount }}</td>
                            <td>{{ p.payment_date }}</td>
                            <td>{{ p.payment_method }}</td>
                            <td>{{ p.notes or "-" }}</td>
                        </tr>
                        {% else %}
                        <tr>
                            <td colspan="5">No payments recorded yet.</td>
                        </tr>
                        {% endfor %}
                    </table>
                </div>
            </div>
        </body>
        </html>
        """, members=members, history=history, total=total,
             today=date.today().isoformat())


@app.route("/attendance", methods=["GET", "POST"])
def attendance():
    with get_db() as conn:
        if request.method == "POST":
            member_id = request.form.get("member_id", type=int)
            attendance_date = date.today().isoformat()

            if not member_id:
                flash("Please select a member.")
                return redirect(url_for("attendance"))

            try:
                conn.execute("""
                    INSERT INTO attendance
                    (member_id, attendance_date, check_in_time)
                    VALUES (?, ?, time('now', 'localtime'))
                """, (member_id, attendance_date))
                flash("Attendance recorded successfully!")
            except sqlite3.IntegrityError:
                flash("Attendance is already recorded for this member today.")

            return redirect(url_for("attendance"))

        members = conn.execute(
            "SELECT id, name FROM members ORDER BY name"
        ).fetchall()

        records = conn.execute("""
            SELECT members.name, attendance.attendance_date,
                   attendance.check_in_time
            FROM attendance
            JOIN members ON members.id = attendance.member_id
            ORDER BY attendance.id DESC
            LIMIT 50
        """).fetchall()

    return render_template_string("""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Gym Attendance</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                
                * {
                    box-sizing: border-box;
                }

                body {
                    background: #0b1020;
                    color: #f1f5f9;
                    font-family: "Segoe UI", Arial, sans-serif;
                    padding: 28px;
                    margin: 0;
                    line-height: 1.6;
                }

                h1 {
                    font-size: clamp(28px, 4vw, 38px);
                    margin: 22px 0;
                    letter-spacing: -1px;
                }

                h2 {
                    font-size: 21px;
                    margin-top: 0;
                    color: #f8fafc;
                }

                .card {
                    background: linear-gradient(145deg, #171f33, #121a2b);
                    border: 1px solid #29354b;
                    padding: 24px;
                    border-radius: 16px;
                    margin: 22px 0;
                    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.18);
                }

                input, select, textarea, button {
                    display: block;
                    width: 100%;
                    padding: 13px 14px;
                    margin: 9px 0 18px;
                    border-radius: 9px;
                    font: inherit;
                }

                input, select, textarea {
                    background: #0c1425;
                    color: #f1f5f9;
                    border: 1px solid #35435b;
                    outline: none;
                    transition: border-color 0.2s, box-shadow 0.2s;
                }

                input:focus, select:focus, textarea:focus {
                    border-color: #a3ff3f;
                    box-shadow: 0 0 0 3px rgba(163, 255, 63, 0.12);
                }

                button {
                    background: linear-gradient(135deg, #a3ff3f, #78e323);
                    color: #10170b;
                    border: none;
                    font-weight: 700;
                    cursor: pointer;
                    transition: transform 0.2s, filter 0.2s;
                }

                button:hover {
                    filter: brightness(1.08);
                    transform: translateY(-1px);
                }

                table {
                    width: 100%;
                    border-collapse: collapse;
                    min-width: 520px;
                }

                th {
                    color: #a3ff3f;
                    background: #202b40;
                    text-transform: uppercase;
                    font-size: 12px;
                    letter-spacing: 0.7px;
                }

                th, td {
                    padding: 14px 16px;
                    border-bottom: 1px solid #29354b;
                    text-align: left;
                }

                tr:hover td {
                    background: rgba(163, 255, 63, 0.035);
                }

                a {
                    color: #a3ff3f;
                    text-decoration: none;
                }

                a:hover {
                    color: white;
                    text-decoration: underline;
                }

                .table-wrap {
                    width: 100%;
                    overflow-x: auto;
                    border-radius: 10px;
                }

                .message {
                    background: #142b22;
                    color: #a3ff3f;
                    padding: 12px 16px;
                    border: 1px solid #28543a;
                    border-radius: 9px;
                }

                @media (max-width: 600px) {
                    body {
                        padding: 14px;
                    }

                    .card {
                        padding: 17px;
                    }
                }
            </style>
        </head>
        <body>
            <a href="/">← Back to Dashboard</a>
            <h1>Attendance Management</h1>

            {% for message in get_flashed_messages() %}
                <p>{{ message }}</p>
            {% endfor %}

            <div class="card">
                <h2>Mark Attendance</h2>
                <form method="POST">
                    <label>Select Member</label>
                    <select name="member_id" required>
                        <option value="">Choose a member</option>
                        {% for m in members %}
                            <option value="{{ m.id }}">{{ m.name }}</option>
                        {% endfor %}
                    </select>
                    <button type="submit">Record Attendance</button>
                </form>
            </div>

            <div class="card">
                <h2>Recent Attendance</h2>
                <table>
                    <tr><th>Member</th><th>Date</th><th>Check-in</th></tr>
                    {% for r in records %}
                    <tr>
                        <td>{{ r.name }}</td>
                        <td>{{ r.attendance_date }}</td>
                        <td>{{ r.check_in_time }}</td>
                    </tr>
                    {% else %}
                    <tr><td colspan="3">No attendance records yet.</td></tr>
                    {% endfor %}
                </table>
            </div>
        </body>
        </html>
    """, members=members, records=records)



if __name__ == "__main__":
    app.run(debug=True)
