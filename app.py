"""
MyFarm — Flask + MySQL Backend
-------------------------------
Endpoints:
  POST /api/register/farm     — create a new farm + admin account
  POST /api/register/account  — add an employee to an existing farm
  POST /api/login             — authenticate; returns farm_name, username, role_label
  GET  /api/stats             — dashboard stat cards (livestock, herds, health)
  GET  /api/livestock/history — monthly head-count for chart
  POST /api/livestock/record  — upsert the current month's head-count
  GET  /api/activity          — recent activity feed
  POST /api/activity          — log a new activity entry
  GET  /                      — serve login.html
  GET  /<filename>            — serve any other static file

Run:
  pip install flask werkzeug mysql-connector-python
  python app.py
  Open: http://localhost:8000
"""

from flask import Flask, request, jsonify, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector
from mysql.connector import IntegrityError as MySQLIntegrityError
import os, re, datetime, random, string, calendar

# ── App ───────────────────────────────────────────────────────────────────────
app  = Flask(__name__, static_folder=".")
PORT = 8000

# ── MySQL config — change password to match your MySQL installation ────────────
DB_CONFIG = {
    "host":     "localhost",
    "user":     "root",
    "password": "Summergirl1@",   # ← replace this
    "database": "myfarm",
    "buffered": True,                    # avoids "unread result" errors
}

# ── Role map — stored as TINYINT in DB, displayed as a label everywhere else ──
#   1 = Admin       — full access to every feature
#   2 = IT Manager  — can manage users, roles, and network settings
#   3 = Farm Manager — day-to-day livestock / herd operations
ROLES = {
    1: "Admin",
    2: "IT Manager",
    3: "Farm Manager",
}

# ── DB helpers ─────────────────────────────────────────────────────────────────
def get_db():
    """Open a fresh MySQL connection."""
    return mysql.connector.connect(**DB_CONFIG)

def get_farm_id(cursor, farm_name: str):
    """Return db_Farm (int) for a given farm_name, or None."""
    cursor.execute("SELECT db_Farm FROM farms WHERE farm_name = %s", (farm_name,))
    row = cursor.fetchone()
    return row[0] if row else None

def next_user_id(cursor) -> int:
    """
    Generate the next sequential user_id.
    This is a human-readable employee number (distinct from db_user_id).
    Starts at 1001 if the table is empty.
    """
    cursor.execute("SELECT COALESCE(MAX(user_id), 1000) AS m FROM users")
    row = cursor.fetchone()
    return (row[0] if row else 1000) + 1

def generate_employee_code(length: int = 6) -> str:
    """Random uppercase alphanumeric code given to employees on registration."""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

# ── Validation helpers ────────────────────────────────────────────────────────
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def validate_user_fields(username: str, password: str) -> str | None:
    if len(username) < 3:
        return "Username must be at least 3 characters."
    if not username.isalnum():
        return "Username may only contain letters and numbers."
    if len(password) < 6:
        return "Password must be at least 6 characters."
    return None

def human_time_ago(ts) -> str:
    """Convert a datetime (or ISO string) to '2 hours ago', 'Yesterday', etc.
    Uses local time to match MySQL's CURRENT_TIMESTAMP, which is stored
    in the server's local timezone, not UTC."""
    if isinstance(ts, str):
        ts = datetime.datetime.fromisoformat(ts)
    delta = datetime.datetime.now() - ts
    secs  = int(delta.total_seconds())
    if secs < 0:    secs = 0   # guard against tiny clock drift
    if secs < 60:   return "Just now"
    if secs < 3600: m = secs // 60;  return f"{m} minute{'s' if m!=1 else ''} ago"
    if delta.days == 0: h = secs//3600; return f"{h} hour{'s' if h!=1 else ''} ago"
    if delta.days == 1: return "Yesterday"
    if delta.days < 7:  return f"{delta.days} days ago"
    return ts.strftime("%b %d, %Y")

# ── Static file serving ───────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory(".", "login.html")

@app.route("/<path:filename>")
def serve_static(filename):
    if ".." in filename:
        return "Forbidden", 403
    return send_from_directory(".", filename)

# ── POST /api/register/farm ───────────────────────────────────────────────────
@app.route("/api/register/farm", methods=["POST"])
def register_farm():
    """
    Creates a new farm and its first Admin user in one step.
    Body: { farm_name, email, username, password }
    """
    data      = request.get_json(silent=True) or {}
    farm_name = data.get("farm_name", "").strip()
    email     = data.get("email",     "").strip().lower()
    username  = data.get("username",  "").strip()
    password  = data.get("password",  "")

    # Validate
    if not all([farm_name, email, username, password]):
        return jsonify({"success": False, "message": "All fields are required."}), 400
    if not EMAIL_RE.match(email):
        return jsonify({"success": False, "message": "Please enter a valid email address."}), 400
    err = validate_user_fields(username, password)
    if err:
        return jsonify({"success": False, "message": err}), 400

    pw_hash       = generate_password_hash(password)
    employee_code = generate_employee_code()   # admins share this with new staff

    conn   = get_db()
    cursor = conn.cursor()
    try:
        # 1. Create the farm
        cursor.execute(
            "INSERT INTO farms (farm_name, employee_code) VALUES (%s, %s)",
            (farm_name, employee_code),
        )
        db_farm = cursor.lastrowid   # the new farm's primary key

        # 2. Create the Admin user (role = 1)
        uid = next_user_id(cursor)
        cursor.execute(
            """INSERT INTO users
               (username, email, password_hash, db_farm, user_id, role)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (username, email, pw_hash, db_farm, uid, 1),
        )

        conn.commit()

        return jsonify({
            "success":       True,
            "message":       "Farm created! Your employee code is: " + employee_code,
            "employee_code": employee_code,
            "farm_name":     farm_name,
            "farm_id":       db_farm,
            "username":      username,
            "user_id":       uid,
            "role":          1,
            "role_label":    ROLES[1],
        }), 201

    except MySQLIntegrityError as exc:
        conn.rollback()
        msg = str(exc)
        if "farm_name" in msg or "farms" in msg:
            return jsonify({"success": False, "message": "A farm with that name already exists."}), 409
        if "username" in msg:
            return jsonify({"success": False, "message": "That username is already taken."}), 409
        if "email" in msg:
            return jsonify({"success": False, "message": "That email is already registered."}), 409
        return jsonify({"success": False, "message": "Registration failed. Please try again."}), 409
    finally:
        cursor.close()
        conn.close()

# ── POST /api/register/account ────────────────────────────────────────────────
@app.route("/api/register/account", methods=["POST"])
def register_account():
    """
    Adds a new employee to an existing farm.
    The farm_id + employee_code must match — both are given to staff by an Admin
    or IT Manager.
    Body: { farm_id, employee_code, username, password }
    Default role is Farm Manager (3); only IT Manager/Admin can change it later.
    """
    data          = request.get_json(silent=True) or {}
    employee_code = data.get("employee_code", "").strip().upper()
    username      = data.get("username",      "").strip()
    password      = data.get("password",      "")

    try:
        farm_id = int(data.get("farm_id", 0))
    except (ValueError, TypeError):
        return jsonify({"success": False, "message": "Farm ID must be a number."}), 400

    if not all([farm_id, employee_code, username, password]):
        return jsonify({"success": False, "message": "All fields are required."}), 400

    err = validate_user_fields(username, password)
    if err:
        return jsonify({"success": False, "message": err}), 400

    conn   = get_db()
    cursor = conn.cursor()
    try:
        # Verify farm_id + employee_code
        cursor.execute(
            "SELECT db_Farm, farm_name FROM farms WHERE db_Farm = %s AND employee_code = %s",
            (farm_id, employee_code),
        )
        farm = cursor.fetchone()
        if not farm:
            return jsonify({
                "success": False,
                "message": "Invalid Farm ID or Employee Code. Contact your Admin.",
            }), 403

        db_farm    = farm[0]
        farm_name  = farm[1]
        pw_hash    = generate_password_hash(password)
        uid        = next_user_id(cursor)

        cursor.execute(
            """INSERT INTO users
               (username, password_hash, db_farm, user_id, role)
               VALUES (%s, %s, %s, %s, %s)""",
            (username, pw_hash, db_farm, uid, 3),  # role 3 = Farm Manager by default
        )
        conn.commit()

        return jsonify({
            "success":    True,
            "message":    f"Account created! Welcome to {farm_name}.",
            "farm_name":  farm_name,
            "farm_id":    db_farm,
            "username":   username,
            "user_id":    uid,
            "role":       3,
            "role_label": ROLES[3],
        }), 201

    except MySQLIntegrityError as exc:
        conn.rollback()
        if "username" in str(exc):
            return jsonify({"success": False, "message": "That username is already taken."}), 409
        return jsonify({"success": False, "message": "Registration failed."}), 409
    finally:
        cursor.close()
        conn.close()

# ── POST /api/login ───────────────────────────────────────────────────────────
@app.route("/api/login", methods=["POST"])
def login():
    data     = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"success": False,
                        "message": "Username and password are required."}), 400

    conn   = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """SELECT u.username, u.password_hash, u.role, u.user_id,
                      f.farm_name, f.db_Farm
               FROM users u
               JOIN farms f ON u.db_farm = f.db_Farm
               WHERE u.username = %s""",
            (username,),
        )
        row = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

    if row and check_password_hash(row[1], password):
        role_int   = row[2]
        role_label = ROLES.get(role_int, "Farm Manager")
        return jsonify({
            "success":    True,
            "message":    f"Welcome back, {row[0]}!",
            "username":   row[0],
            "user_id":    row[3],
            "farm_name":  row[4],
            "farm_id":    row[5],
            "role":       role_int,       # integer (for permission checks)
            "role_label": role_label,     # human label (for the UI badge)
        })

    return jsonify({"success": False,
                    "message": "Invalid username or password."}), 401

# ── GET /api/stats ────────────────────────────────────────────────────────────
@app.route("/api/stats")
def get_stats():
    farm_name = request.args.get("farm_name", "").strip()
    if not farm_name:
        return jsonify({"error": "farm_name is required"}), 400

    conn   = get_db()
    cursor = conn.cursor()
    try:
        db_farm = get_farm_id(cursor, farm_name)
        if not db_farm:
            return jsonify({"error": "Farm not found"}), 404

        cursor.execute(
            "SELECT COUNT(*), COALESCE(SUM(head_count), 0) FROM herds WHERE db_farm = %s",
            (db_farm,),
        )
        herd_count, total_now = cursor.fetchone()

        # Previous month's snapshot is used only for the % change figure.
        # Must EXCLUDE the current year/month — add_animal/add_herd upsert
        # today's snapshot on every call, so without this exclusion the
        # "most recent" row is always this month's own total, comparing
        # it to itself and permanently showing 0.00% change.
        today = datetime.date.today()
        cursor.execute(
            """SELECT head_count FROM livestock_history
               WHERE db_farm = %s
                 AND (`year` < %s OR (`year` = %s AND `month` < %s))
               ORDER BY `year` DESC, `month` DESC LIMIT 1""",
            (db_farm, today.year, today.year, today.month),
        )
        prev_row = cursor.fetchone()

        cursor.execute(
            """SELECT score FROM health_records WHERE db_farm = %s
               ORDER BY recorded_at DESC LIMIT 1""",
            (db_farm,),
        )
        health_row = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

    total   = total_now
    prev    = prev_row[0] if prev_row else total
    pct_chg = round((total - prev) / prev * 100, 1) if prev > 0 else 0.0

    return jsonify({
        "total_livestock":  total,
        "livestock_change": pct_chg,
        "total_herds":      herd_count,
        "health_score":     health_row[0] if health_row else 0,
    })

# ── GET /api/livestock/history ────────────────────────────────────────────────
@app.route("/api/livestock/history")
def get_livestock_history():
    farm_name = request.args.get("farm_name", "").strip()
    if not farm_name:
        return jsonify({"error": "farm_name is required"}), 400

    limit = min(int(request.args.get("limit", 12)), 24)

    conn   = get_db()
    cursor = conn.cursor()
    try:
        db_farm = get_farm_id(cursor, farm_name)
        if not db_farm:
            return jsonify({"error": "Farm not found"}), 404

        cursor.execute(
            """SELECT `year`, `month`, head_count FROM livestock_history
               WHERE db_farm = %s ORDER BY `year` ASC, `month` ASC LIMIT %s""",
            (db_farm, limit),
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun",
                   "Jul","Aug","Sep","Oct","Nov","Dec"]
    return jsonify({
        "months": [MONTH_NAMES[r[1] - 1] for r in rows],
        "counts": [r[2] for r in rows],
    })

# ── POST /api/livestock/record ────────────────────────────────────────────────
@app.route("/api/livestock/record", methods=["POST"])
def add_livestock_record():
    data      = request.get_json(silent=True) or {}
    farm_name = data.get("farm_name", "").strip()
    try:
        head_count = int(data.get("head_count", 0))
    except (ValueError, TypeError):
        return jsonify({"success": False, "message": "head_count must be an integer"}), 400

    if not farm_name or head_count < 0:
        return jsonify({"success": False,
                        "message": "farm_name and head_count are required"}), 400

    now    = datetime.datetime.now()
    conn   = get_db()
    cursor = conn.cursor()
    try:
        db_farm = get_farm_id(cursor, farm_name)
        if not db_farm:
            return jsonify({"success": False, "message": "Farm not found"}), 404

        cursor.execute(
            """INSERT INTO livestock_history (db_farm, `year`, `month`, head_count)
               VALUES (%s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE head_count = VALUES(head_count)""",
            (db_farm, now.year, now.month, head_count),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    return jsonify({"success": True, "message": "Record saved."})

# ── GET /api/activity ─────────────────────────────────────────────────────────
@app.route("/api/activity")
def get_activity():
    farm_name = request.args.get("farm_name", "").strip()
    if not farm_name:
        return jsonify({"error": "farm_name is required"}), 400

    limit = min(int(request.args.get("limit", 8)), 20)

    conn   = get_db()
    cursor = conn.cursor()
    try:
        db_farm = get_farm_id(cursor, farm_name)
        if not db_farm:
            return jsonify({"error": "Farm not found"}), 404

        cursor.execute(
            """SELECT title, description, created_at FROM activity_log
               WHERE db_farm = %s ORDER BY created_at DESC LIMIT %s""",
            (db_farm, limit),
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    return jsonify({
        "items": [
            {
                "title":       r[0],
                "description": r[1],
                "time":        human_time_ago(r[2]),
            }
            for r in rows
        ]
    })

# ── POST /api/activity ────────────────────────────────────────────────────────
@app.route("/api/activity", methods=["POST"])
def log_activity():
    data      = request.get_json(silent=True) or {}
    farm_name = data.get("farm_name", "").strip()
    title     = data.get("title",     "").strip()
    desc      = data.get("description", "").strip()

    if not farm_name or not title:
        return jsonify({"success": False,
                        "message": "farm_name and title are required"}), 400

    conn   = get_db()
    cursor = conn.cursor()
    try:
        db_farm = get_farm_id(cursor, farm_name)
        if not db_farm:
            return jsonify({"success": False, "message": "Farm not found"}), 404

        cursor.execute(
            "INSERT INTO activity_log (db_farm, title, description) VALUES (%s, %s, %s)",
            (db_farm, title, desc),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    return jsonify({"success": True, "message": "Activity logged."})

# ── GET /api/herds ────────────────────────────────────────────────────────────
@app.route("/api/herds")
def get_herds():
    farm_name = request.args.get("farm_name", "").strip()
    if not farm_name:
        return jsonify({"error": "farm_name is required"}), 400

    conn   = get_db()
    cursor = conn.cursor()
    try:
        db_farm = get_farm_id(cursor, farm_name)
        if not db_farm:
            return jsonify({"error": "Farm not found"}), 404

        cursor.execute(
            """SELECT id, herd_name, head_count FROM herds
               WHERE db_farm = %s ORDER BY herd_name""",
            (db_farm,),
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    total_animals = sum(r[2] for r in rows)
    return jsonify({
        "herds": [
            {
                "id":         r[0],
                "herd_name":  r[1],
                "head_count": r[2],
                "pct": round(r[2] / total_animals * 100, 1) if total_animals > 0 else 0,
            }
            for r in rows
        ],
        "total_herds":   len(rows),
        "total_animals": total_animals,
    })

# ── POST /api/herds ───────────────────────────────────────────────────────────
@app.route("/api/herds", methods=["POST"])
def add_herd():
    data      = request.get_json(silent=True) or {}
    farm_name = data.get("farm_name", "").strip()
    herd_name = data.get("herd_name", "").strip()

    try:
        head_count = int(data.get("head_count", 0) or 0)
    except (ValueError, TypeError):
        return jsonify({"success": False, "message": "Head count must be a number."}), 400

    if not farm_name or not herd_name:
        return jsonify({"success": False,
                        "message": "Farm name and herd name are required."}), 400
    if head_count < 0:
        return jsonify({"success": False, "message": "Head count cannot be negative."}), 400

    conn   = get_db()
    cursor = conn.cursor()
    try:
        db_farm = get_farm_id(cursor, farm_name)
        if not db_farm:
            return jsonify({"success": False, "message": "Farm not found."}), 404

        cursor.execute(
            "INSERT INTO herds (db_farm, herd_name, head_count) VALUES (%s, %s, %s)",
            (db_farm, herd_name, head_count),
        )
        herd_id = cursor.lastrowid

        # Keep the trend chart's current-month snapshot in sync
        cursor.execute(
            "SELECT COALESCE(SUM(head_count), 0) FROM herds WHERE db_farm = %s",
            (db_farm,),
        )
        farm_total = cursor.fetchone()[0]
        now = datetime.datetime.now()
        cursor.execute(
            """INSERT INTO livestock_history (db_farm, `year`, `month`, head_count)
               VALUES (%s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE head_count = VALUES(head_count)""",
            (db_farm, now.year, now.month, farm_total),
        )

        cursor.execute(
            "INSERT INTO activity_log (db_farm, title, description) VALUES (%s, %s, %s)",
            (db_farm, f"New herd created: {herd_name}",
             f"Starting head count: {head_count}"),
        )
        conn.commit()

    except MySQLIntegrityError:
        conn.rollback()
        return jsonify({"success": False, "message": "Failed to create herd."}), 409
    finally:
        cursor.close()
        conn.close()

    return jsonify({
        "success":  True,
        "message":  f'Herd "{herd_name}" created successfully.',
        "id":       herd_id,
    }), 201

# ── GET /api/breeds ────────────────────────────────────────────────────────────
@app.route("/api/breeds")
def get_breeds():
    farm_name = request.args.get("farm_name", "").strip()
    if not farm_name:
        return jsonify({"error": "farm_name is required"}), 400

    conn   = get_db()
    cursor = conn.cursor()
    try:
        db_farm = get_farm_id(cursor, farm_name)
        if not db_farm:
            return jsonify({"error": "Farm not found"}), 404

        cursor.execute(
            """SELECT b.id, b.breed_name, COUNT(a.id) AS animal_count
               FROM breeds b
               LEFT JOIN animals a
                      ON a.breed = b.breed_name AND a.db_farm = b.db_farm
               WHERE b.db_farm = %s
               GROUP BY b.id, b.breed_name
               ORDER BY b.breed_name""",
            (db_farm,),
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    total_animals = sum(r[2] for r in rows)
    return jsonify({
        "breeds": [
            {
                "id":           r[0],
                "breed_name":   r[1],
                "animal_count": r[2],
                "pct": round(r[2] / total_animals * 100, 1) if total_animals > 0 else 0,
            }
            for r in rows
        ],
        "total_breeds": len(rows),
    })

# ── POST /api/breeds ───────────────────────────────────────────────────────────
@app.route("/api/breeds", methods=["POST"])
def add_breed():
    data       = request.get_json(silent=True) or {}
    farm_name  = data.get("farm_name",  "").strip()
    breed_name = data.get("breed_name", "").strip()

    if not farm_name or not breed_name:
        return jsonify({"success": False,
                        "message": "Farm name and breed name are required."}), 400

    conn   = get_db()
    cursor = conn.cursor()
    try:
        db_farm = get_farm_id(cursor, farm_name)
        if not db_farm:
            return jsonify({"success": False, "message": "Farm not found."}), 404

        cursor.execute(
            "INSERT INTO breeds (db_farm, breed_name) VALUES (%s, %s)",
            (db_farm, breed_name),
        )
        breed_id = cursor.lastrowid
        conn.commit()

    except MySQLIntegrityError:
        conn.rollback()
        return jsonify({"success": False,
                        "message": f'"{breed_name}" is already in your breed list.'}), 409
    finally:
        cursor.close()
        conn.close()

    return jsonify({
        "success":    True,
        "message":    f'Breed "{breed_name}" added.',
        "id":         breed_id,
        "breed_name": breed_name,
    }), 201

# ── GET /api/animals ──────────────────────────────────────────────────────────
@app.route("/api/animals")
def get_animals():
    farm_name   = request.args.get("farm_name", "").strip()
    herd_id     = request.args.get("herd_id",   None)
    gender      = request.args.get("gender",    None)
    tag_search  = request.args.get("tag",       None)
    breed_search = request.args.get("breed",    None)
    sort_by     = request.args.get("sort",      "tag_number")
    limit       = min(int(request.args.get("limit",  50)), 200)
    offset      = int(request.args.get("offset", 0))

    if not farm_name:
        return jsonify({"error": "farm_name is required"}), 400

    # Whitelist sort columns to prevent SQL injection
    safe_sorts = {
        "tag_number": "a.tag_number",
        "dob":        "a.date_of_birth",
        "weight":     "a.weight",
        "herd":       "h.herd_name",
        "gender":     "a.gender",
        "breed":      "a.breed",
    }
    order = safe_sorts.get(sort_by, "a.tag_number")

    conditions = ["a.db_farm = %s"]
    params     = []

    conn   = get_db()
    cursor = conn.cursor()
    try:
        db_farm = get_farm_id(cursor, farm_name)
        if not db_farm:
            return jsonify({"error": "Farm not found"}), 404

        params.append(db_farm)

        if herd_id:
            conditions.append("a.herd_id = %s")
            params.append(int(herd_id))
        if gender and gender in ("Male", "Female"):
            conditions.append("a.gender = %s")
            params.append(gender)
        if tag_search:
            conditions.append("a.tag_number LIKE %s")
            params.append(f"%{tag_search}%")
        if breed_search:
            conditions.append("a.breed LIKE %s")
            params.append(f"%{breed_search}%")

        where = " AND ".join(conditions)

        # Total count (for pagination)
        cursor.execute(
            f"SELECT COUNT(*) FROM animals a LEFT JOIN herds h ON a.herd_id = h.id WHERE {where}",
            params,
        )
        total = cursor.fetchone()[0]

        # Paginated results
        cursor.execute(
            f"""SELECT a.id, a.tag_number, a.gender, a.breed, a.date_of_birth,
                       a.weight, h.herd_name, a.notes
                FROM animals a
                LEFT JOIN herds h ON a.herd_id = h.id
                WHERE {where}
                ORDER BY {order}
                LIMIT %s OFFSET %s""",
            params + [limit, offset],
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    def calc_age(dob) -> str:
        if not dob:
            return "—"
        today = datetime.date.today()

        if dob > today:
            return "N/A"

        years  = today.year  - dob.year
        months = today.month - dob.month
        days   = today.day   - dob.day

        if days < 0:
            months -= 1
            prev_month = today.month - 1 or 12
            prev_year  = today.year if today.month > 1 else today.year - 1
            days += calendar.monthrange(prev_year, prev_month)[1]

        if months < 0:
            years  -= 1
            months += 12

        parts = []
        if years  > 0: parts.append(f"{years} year{'s'  if years  != 1 else ''}")
        if months > 0: parts.append(f"{months} month{'s' if months != 1 else ''}")
        if days   > 0 or not parts:
            parts.append(f"{days} day{'s' if days != 1 else ''}")

        return ", ".join(parts)

    animals = [
        {
            "id":            r[0],
            "tag_number":    r[1],
            "gender":        r[2],
            "breed":         r[3] or "—",
            "date_of_birth": r[4].isoformat() if r[4] else None,
            "age":           calc_age(r[4]),
            "weight":        float(r[5]) if r[5] is not None else None,
            "herd_name":     r[6] or "—",
            "notes":         r[7] or "",
        }
        for r in rows
    ]

    return jsonify({"animals": animals, "total": total})

# ── POST /api/animals ─────────────────────────────────────────────────────────
@app.route("/api/animals", methods=["POST"])
def add_animal():
    data       = request.get_json(silent=True) or {}
    farm_name  = data.get("farm_name",    "").strip()
    tag_number = data.get("tag_number",   "").strip()
    gender     = data.get("gender",       "").strip()
    breed      = data.get("breed",        "").strip()
    dob        = data.get("date_of_birth","")
    weight     = data.get("weight",       None)
    herd_id    = data.get("herd_id",      None)
    notes      = data.get("notes",        "").strip()

    if not all([farm_name, tag_number, gender, dob]):
        return jsonify({"success": False,
                        "message": "Tag number, gender, and date of birth are required."}), 400
    if gender not in ("Male", "Female"):
        return jsonify({"success": False, "message": "Gender must be Male or Female."}), 400

    try:
        weight = float(weight) if weight not in (None, "", 0) else None
    except (ValueError, TypeError):
        return jsonify({"success": False, "message": "Weight must be a number."}), 400

    conn   = get_db()
    cursor = conn.cursor()
    try:
        db_farm = get_farm_id(cursor, farm_name)
        if not db_farm:
            return jsonify({"success": False, "message": "Farm not found."}), 404

        # Verify herd belongs to this farm
        if herd_id:
            cursor.execute(
                "SELECT id FROM herds WHERE id = %s AND db_farm = %s",
                (int(herd_id), db_farm),
            )
            if not cursor.fetchone():
                return jsonify({"success": False, "message": "Invalid herd."}), 400

        cursor.execute(
            """INSERT INTO animals
               (db_farm, tag_number, gender, breed, date_of_birth, weight, herd_id, notes)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (db_farm, tag_number, gender, breed or None, dob, weight, herd_id or None, notes or None),
        )
        animal_id = cursor.lastrowid

        # Update herd head count
        if herd_id:
            cursor.execute(
                "UPDATE herds SET head_count = head_count + 1 WHERE id = %s",
                (int(herd_id),),
            )

        # Snapshot the farm's current total into livestock_history for this
        # month, so the dashboard trend chart reflects real growth over time.
        cursor.execute(
            "SELECT COALESCE(SUM(head_count), 0) FROM herds WHERE db_farm = %s",
            (db_farm,),
        )
        farm_total = cursor.fetchone()[0]
        now = datetime.datetime.now()
        cursor.execute(
            """INSERT INTO livestock_history (db_farm, `year`, `month`, head_count)
               VALUES (%s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE head_count = VALUES(head_count)""",
            (db_farm, now.year, now.month, farm_total),
        )

        # Log the addition
        herd_label = ""
        if herd_id:
            cursor.execute("SELECT herd_name FROM herds WHERE id = %s", (int(herd_id),))
            row = cursor.fetchone()
            herd_label = f" to {row[0]}" if row else ""

        cursor.execute(
            "INSERT INTO activity_log (db_farm, title, description) VALUES (%s, %s, %s)",
            (db_farm, f"Animal #{tag_number} registered",
             f"{gender} animal added{herd_label}"),
        )
        conn.commit()

    except MySQLIntegrityError as exc:
        conn.rollback()
        if "uq_farm_tag" in str(exc) or "tag_number" in str(exc):
            return jsonify({"success": False,
                            "message": f'Tag "{tag_number}" is already in use on this farm.'}), 409
        return jsonify({"success": False, "message": "Failed to add animal."}), 409
    finally:
        cursor.close()
        conn.close()

    return jsonify({"success": True,
                    "message": f"Animal #{tag_number} added successfully.",
                    "id": animal_id}), 201

# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print()
    print("🌱  MyFarm (MySQL backend) — http://localhost:" + str(PORT))
    print("    ⚠️  Open the URL above in your browser — not the HTML file directly.")
    print()
    app.run(debug=True, port=PORT)
