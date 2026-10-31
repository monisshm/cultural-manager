import hashlib
import hmac
import os
import secrets
import sqlite3
import subprocess
import tempfile
import threading
from datetime import date
from functools import wraps
from pathlib import Path

from flask import Flask, g, jsonify, request, send_from_directory, session


BASE_DIR = Path(__file__).resolve().parent
DATABASE = Path(os.environ.get("CULTURAL_FEST_DATABASE", BASE_DIR / "cultural_fest.db"))
JAVA_SOURCE = BASE_DIR / "EventManager.java"
JAVA_BUILD_DIR = Path(tempfile.gettempdir()) / "campus-culture-java"
JAVA_LOCK = threading.Lock()
JAVA_COMPILED = False
ROLES = {"admin", "organizer", "participant", "volunteer"}
PASSWORD_ITERATIONS = 310_000

app = Flask(__name__)
app.secret_key = os.environ.get("CULTURAL_FEST_SECRET") or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")


def get_db():
    if "db" not in g:
        DATABASE.parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_error=None):
    database = g.pop("db", None)
    if database is not None:
        database.close()


def initialize_database():
    with app.app_context():
        db = get_db()
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                name TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('admin', 'organizer', 'participant', 'volunteer')),
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                date TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                venue TEXT NOT NULL,
                capacity INTEGER NOT NULL,
                description TEXT NOT NULL,
                created_by INTEGER NOT NULL REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS registrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                status TEXT NOT NULL DEFAULT 'registered' CHECK (status IN ('registered', 'cancelled')),
                UNIQUE(event_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS volunteer_assignments (
                event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                assigned_by INTEGER NOT NULL REFERENCES users(id),
                PRIMARY KEY(event_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS updates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL CHECK (kind IN ('announcement', 'result')),
                event_id INTEGER REFERENCES events(id) ON DELETE SET NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                created_by INTEGER NOT NULL REFERENCES users(id),
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )
        for username, name, role, password in (
            ("admin", "Fest Administrator", "admin", "admin123"),
            ("organizer", "Fest Organizer", "organizer", "organizer123"),
            ("participant", "Fest Participant", "participant", "participant123"),
            ("volunteer", "Fest Volunteer", "volunteer", "volunteer123"),
        ):
            exists = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
            if not exists:
                salt = secrets.token_hex(16)
                password_hash = hash_password(password, salt)
                db.execute(
                    "INSERT INTO users (username, name, role, password_hash, password_salt) VALUES (?, ?, ?, ?, ?)",
                    (username, name, role, password_hash, salt),
                )
        db.commit()


def hash_password(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), PASSWORD_ITERATIONS).hex()


def require_login(handler):
    @wraps(handler)
    def wrapped(*args, **kwargs):
        user_id = session.get("user_id")
        if not user_id:
            return jsonify(error="Sign in is required."), 401
        user = get_db().execute("SELECT id, username, name, role FROM users WHERE id = ?", (user_id,)).fetchone()
        if user is None:
            session.clear()
            return jsonify(error="Your account is no longer available. Please sign in again."), 401
        g.user = user
        return handler(*args, **kwargs)
    return wrapped


def require_roles(*roles):
    def decorator(handler):
        @wraps(handler)
        @require_login
        def wrapped(*args, **kwargs):
            if g.user["role"] not in roles:
                return jsonify(error="You do not have permission to perform this action."), 403
            return handler(*args, **kwargs)
        return wrapped
    return decorator


def json_body():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ValueError("A valid JSON object is required.")
    return payload


def required_text(payload, key, label, maximum):
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required.")
    value = value.strip()
    if len(value) > maximum:
        raise ValueError(f"{label} must be {maximum} characters or fewer.")
    return value


def run_java(*arguments):
    global JAVA_COMPILED
    with JAVA_LOCK:
        if not JAVA_COMPILED:
            JAVA_BUILD_DIR.mkdir(parents=True, exist_ok=True)
            compile_result = subprocess.run(
                ["javac", "-encoding", "UTF-8", "-d", str(JAVA_BUILD_DIR), str(JAVA_SOURCE)],
                capture_output=True, text=True, check=False,
            )
            if compile_result.returncode:
                detail = compile_result.stderr.strip() or compile_result.stdout.strip()
                raise RuntimeError(f"Could not compile EventManager.java. Check that a JDK is installed. {detail}")
            JAVA_COMPILED = True
    result = subprocess.run(
        ["java", "-cp", str(JAVA_BUILD_DIR), "EventManager", *map(str, arguments)],
        capture_output=True, text=True, check=False,
    )
    if result.returncode:
        raise ValueError(result.stderr.strip() or "Java event validation failed.")
    return result.stdout.strip()


def event_values(payload):
    name = required_text(payload, "name", "Event name", 100)
    category = required_text(payload, "category", "Category", 50)
    event_date = required_text(payload, "date", "Date", 10)
    start_time = required_text(payload, "start_time", "Start time", 5)
    end_time = required_text(payload, "end_time", "End time", 5)
    venue = required_text(payload, "venue", "Venue", 100)
    description = required_text(payload, "description", "Description", 1000)
    capacity = payload.get("capacity")
    if isinstance(capacity, bool) or not isinstance(capacity, int):
        raise ValueError("Registration limit must be a whole number.")
    run_java("validate-event", name, category, event_date, start_time, end_time, venue, capacity)
    return name, category, event_date, start_time, end_time, venue, capacity, description


def event_for_manager(event_id):
    event = get_db().execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    if event is None:
        return None, (jsonify(error="Event not found."), 404)
    if g.user["role"] != "admin" and event["created_by"] != g.user["id"]:
        return None, (jsonify(error="You can only manage events that you created."), 403)
    return event, None


def public_event(event):
    count = event["registration_count"]
    return {
        "id": event["id"], "name": event["name"], "category": event["category"],
        "date": event["date"], "start_time": event["start_time"], "end_time": event["end_time"],
        "venue": event["venue"], "capacity": event["capacity"], "description": event["description"],
        "created_by": event["created_by"], "registration_count": count,
        "my_status": event["my_status"], "volunteer_assigned": bool(event["volunteer_assigned"]),
    }


@app.get("/")
def home():
    return send_from_directory(BASE_DIR, "index.html")


@app.get("/<path:filename>")
def static_files(filename):
    if filename not in {"style.css", "script.js"}:
        return jsonify(error="File not found."), 404
    return send_from_directory(BASE_DIR, filename)


@app.post("/api/login")
def login():
    try:
        payload = json_body()
        username = required_text(payload, "username", "Username", 30)
        password = payload.get("password")
        if not isinstance(password, str) or not password:
            raise ValueError("Password is required.")
        user = get_db().execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if user is None or not hmac.compare_digest(hash_password(password, user["password_salt"]), user["password_hash"]):
            return jsonify(error="Incorrect username or password."), 401
        session.clear()
        session["user_id"] = user["id"]
        return jsonify(user={"id": user["id"], "name": user["name"], "username": user["username"], "role": user["role"]})
    except ValueError as error:
        return jsonify(error=str(error)), 400


@app.post("/api/signup")
def signup():
    try:
        payload = json_body()
        name = required_text(payload, "name", "Full name", 80)
        username = required_text(payload, "username", "Username", 30)
        password = payload.get("password")
        role = payload.get("role")
        if len(username) < 3 or not all(char.isalnum() or char in "_-" for char in username):
            raise ValueError("Username must be 3–30 letters, numbers, underscores, or hyphens.")
        if not isinstance(password, str) or len(password) < 8:
            raise ValueError("Password must be at least 8 characters.")
        if role not in {"organizer", "participant", "volunteer"}:
            raise ValueError("Choose Organizer, Participant, or Volunteer as your role.")
        salt = secrets.token_hex(16)
        db = get_db()
        try:
            cursor = db.execute(
                "INSERT INTO users (username, name, role, password_hash, password_salt) VALUES (?, ?, ?, ?, ?)",
                (username, name, role, hash_password(password, salt), salt),
            )
            db.commit()
        except sqlite3.IntegrityError:
            return jsonify(error="That username is already in use."), 409
        session.clear()
        session["user_id"] = cursor.lastrowid
        return jsonify(user={"id": cursor.lastrowid, "name": name, "username": username, "role": role}), 201
    except ValueError as error:
        return jsonify(error=str(error)), 400


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@app.get("/api/me")
@require_login
def me():
    return jsonify(user=dict(g.user))


@app.get("/api/events")
@require_login
def list_events():
    rows = get_db().execute(
        """
        SELECT e.*, COUNT(DISTINCT CASE WHEN r.status = 'registered' THEN r.id END) AS registration_count,
               COALESCE(MAX(CASE WHEN r.user_id = ? THEN r.status END), '') AS my_status,
               EXISTS(SELECT 1 FROM volunteer_assignments va WHERE va.event_id = e.id AND va.user_id = ?) AS volunteer_assigned
        FROM events e
        LEFT JOIN registrations r ON r.event_id = e.id
        GROUP BY e.id
        ORDER BY e.date, e.start_time, e.name
        """,
        (g.user["id"], g.user["id"]),
    ).fetchall()
    return jsonify(events=[public_event(row) for row in rows])


@app.post("/api/events")
@require_roles("admin", "organizer")
def create_event():
    try:
        values = event_values(json_body())
        db = get_db()
        cursor = db.execute(
            "INSERT INTO events (name, category, date, start_time, end_time, venue, capacity, description, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (*values, g.user["id"]),
        )
        db.commit()
        return jsonify(id=cursor.lastrowid), 201
    except ValueError as error:
        return jsonify(error=str(error)), 400
    except RuntimeError as error:
        app.logger.exception("Java event validation could not run")
        return jsonify(error=str(error)), 500


@app.route("/api/events/<int:event_id>", methods=["PUT", "DELETE"])
@require_roles("admin", "organizer")
def manage_event(event_id):
    event, error_response = event_for_manager(event_id)
    if error_response:
        return error_response
    if request.method == "DELETE":
        db = get_db()
        db.execute("DELETE FROM events WHERE id = ?", (event_id,))
        db.commit()
        return jsonify(ok=True)
    try:
        values = event_values(json_body())
        registrations = get_db().execute(
            "SELECT COUNT(*) FROM registrations WHERE event_id=? AND status='registered'",
            (event_id,),
        ).fetchone()[0]
        run_java("validate-capacity", values[6], registrations)
        db = get_db()
        db.execute(
            "UPDATE events SET name=?, category=?, date=?, start_time=?, end_time=?, venue=?, capacity=?, description=? WHERE id=?",
            (*values, event_id),
        )
        db.commit()
        return jsonify(ok=True)
    except ValueError as error:
        return jsonify(error=str(error)), 400
    except RuntimeError as error:
        app.logger.exception("Java event validation could not run")
        return jsonify(error=str(error)), 500


@app.route("/api/events/<int:event_id>/registrations", methods=["POST", "DELETE"])
@require_roles("participant")
def registration(event_id):
    db = get_db()
    db.execute("BEGIN IMMEDIATE")
    event = db.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    if event is None:
        db.rollback()
        return jsonify(error="Event not found."), 404
    if request.method == "DELETE":
        db.execute(
            "UPDATE registrations SET status='cancelled' WHERE event_id=? AND user_id=? AND status='registered'",
            (event_id, g.user["id"]),
        )
        db.commit()
        return jsonify(ok=True)
    try:
        existing = db.execute(
            "SELECT status FROM registrations WHERE event_id=? AND user_id=?",
            (event_id, g.user["id"]),
        ).fetchone()
        count = db.execute(
            "SELECT COUNT(*) FROM registrations WHERE event_id=? AND status='registered'",
            (event_id,),
        ).fetchone()[0]
        run_java("can-register", event["capacity"], count, existing["status"] if existing else "none")
        if existing:
            db.execute("UPDATE registrations SET status='registered' WHERE event_id=? AND user_id=?", (event_id, g.user["id"]))
        else:
            db.execute("INSERT INTO registrations (event_id, user_id) VALUES (?, ?)", (event_id, g.user["id"]))
        db.commit()
        return jsonify(ok=True), 201
    except ValueError as error:
        db.rollback()
        return jsonify(error=str(error)), 400
    except RuntimeError as error:
        db.rollback()
        app.logger.exception("Java registration check could not run")
        return jsonify(error=str(error)), 500


@app.post("/api/events/<int:event_id>/volunteers")
@require_roles("admin", "organizer")
def assign_volunteer(event_id):
    _, error_response = event_for_manager(event_id)
    if error_response:
        return error_response
    try:
        payload = json_body()
        username = required_text(payload, "username", "Volunteer username", 30)
        volunteer = get_db().execute("SELECT id, name, role FROM users WHERE username=?", (username,)).fetchone()
        if volunteer is None or volunteer["role"] != "volunteer":
            raise ValueError("No volunteer account exists with that username.")
        event = get_db().execute("SELECT name FROM events WHERE id=?", (event_id,)).fetchone()
        run_java("validate-assignment", event["name"], volunteer["name"])
        get_db().execute(
            "INSERT OR IGNORE INTO volunteer_assignments (event_id, user_id, assigned_by) VALUES (?, ?, ?)",
            (event_id, volunteer["id"], g.user["id"]),
        )
        get_db().commit()
        return jsonify(ok=True), 201
    except ValueError as error:
        return jsonify(error=str(error)), 400
    except RuntimeError as error:
        app.logger.exception("Java assignment validation could not run")
        return jsonify(error=str(error)), 500


@app.get("/api/updates")
@require_login
def list_updates():
    rows = get_db().execute(
        """
        SELECT u.*, e.name AS event_name FROM updates u
        LEFT JOIN events e ON e.id = u.event_id
        ORDER BY u.created_at DESC, u.id DESC
        """
    ).fetchall()
    return jsonify(updates=[{
        "id": row["id"], "kind": row["kind"], "title": row["title"], "body": row["body"],
        "event_name": row["event_name"], "created_at": row["created_at"],
    } for row in rows])


@app.post("/api/updates")
@require_roles("admin", "organizer")
def create_update():
    try:
        payload = json_body()
        kind = payload.get("kind")
        if kind not in {"announcement", "result"}:
            raise ValueError("Choose Announcement or Competition result.")
        title = required_text(payload, "title", "Title", 120)
        body = required_text(payload, "body", "Details", 2000)
        event_id = payload.get("event_id")
        if event_id is not None:
            if isinstance(event_id, bool) or not isinstance(event_id, int):
                raise ValueError("Choose a valid related event.")
            if get_db().execute("SELECT id FROM events WHERE id=?", (event_id,)).fetchone() is None:
                raise ValueError("The selected event no longer exists.")
        get_db().execute(
            "INSERT INTO updates (kind, event_id, title, body, created_by) VALUES (?, ?, ?, ?, ?)",
            (kind, event_id, title, body, g.user["id"]),
        )
        get_db().commit()
        return jsonify(ok=True), 201
    except ValueError as error:
        return jsonify(error=str(error)), 400


@app.get("/api/reports")
@require_roles("admin", "organizer")
def reports():
    rows = get_db().execute(
        """
        SELECT e.id, e.name, e.date, e.venue, e.capacity,
               COUNT(CASE WHEN r.status='registered' THEN 1 END) AS registration_count
        FROM events e LEFT JOIN registrations r ON r.event_id=e.id
        GROUP BY e.id ORDER BY e.date, e.name
        """
    ).fetchall()
    return jsonify(reports=[dict(row) for row in rows])


initialize_database()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False)
