from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, get_flashed_messages, jsonify,
    Response
)
import csv
import json
from functools import wraps

import threading
import sqlite3
import os
import json
import time
from datetime import datetime

# -----------------------------------------------------------------------------
# Configuration and Setup
# -----------------------------------------------------------------------------
app = Flask(__name__, template_folder="templates3")
app.secret_key = "your-secret-key"
DB_FILE = "database.db"
app.jinja_env.globals.update(zip=zip)

from flask import request

@app.before_request
def require_login():
    allowed_routes = ['login', 'register', 'static', 'reset', 'logout', 'formmaker_view', 'home']
    if not session.get('logged_in'):
        # Special case: redirect root URL to home instead of login
        if request.endpoint == 'root_redirect':
            return redirect(url_for('home'))
        # Allow access to formmaker_view if shared=1 query param is present
        if request.endpoint == 'formmaker_view' and request.args.get('shared') == '1':
            return
        # Block access to all other routes except allowed_routes
        if request.endpoint not in allowed_routes:
            return redirect(url_for('login'))
    else:
        # User is logged in, allow access to all routes except explicitly excluded ones
        pass
                    
@app.route("/reset")
def reset():
    for key in ("form_fields", "form_title", "form_description", "user_name", "editing_form_id"):
        session.pop(key, None)
    return redirect(url_for("firstpage"))

def init_db():
    """Create the submissions and user tables (if not exists)."""
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user TEXT,
                form_title TEXT,
                submitted_at TEXT,
                form_description TEXT,
                form_structure TEXT,
                logo_data TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS user (
                uid INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                phone TEXT,
                is_admin INTEGER DEFAULT 0,
                create_date TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
    
init_db()

# Removed add_test_user function as per user request to avoid automatic test user insertion
# def add_test_user():
#     retries = 5
#     delay = 0.2
#     for attempt in range(retries):
#         try:
#             with get_db() as conn:
#                 c = conn.cursor()
#                 c.execute("SELECT * FROM user WHERE email=?", ("test@gmail.com",))
#                 if not c.fetchone():
#                     c.execute("INSERT INTO user (uid, name, email, password) VALUES (?, ?, ?, ?)", (35, "test", "test@gmail.com", "test@gmail.com"))
#                     conn.commit()
#                     print("Test user added: test@gmail.com / test@gmail.com with uid=35")
#             break
#         except sqlite3.OperationalError as e:
#             if "database is locked" in str(e):
#                 time.sleep(delay)
#             else:
#                 raise

# Removed call to add_test_user() as function is commented out
# add_test_user()
# add_test_user()

def format_datetime_ddmmyyyy(value):
    try:
        dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%d%m%Y %H%M%S")
    except Exception:
        return value

app.jinja_env.filters['format_datetime_ddmmyyyy'] = format_datetime_ddmmyyyy
    
def init_response_table(form_id):
    table_name = f"form_{form_id}_responses"
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                submitted_at TEXT DEFAULT CURRENT_TIMESTAMP,
                data TEXT
            )
        """)
        conn.commit()

def create_dynamic_table(form_id, field_definitions, conn=None):
    table_name = f"form_{form_id}_responses"
    columns = ["id INTEGER PRIMARY KEY AUTOINCREMENT"]

    for field in field_definitions:
        field_name = field["name"]
        field_type = field.get("type", "text")
        if field_type in ["number", "range"]:
            sql_type = "REAL"
        else:
            sql_type = "TEXT"
        columns.append(f'"{field_name}" {sql_type}')

    columns.append("submitted_at TEXT")
    create_stmt = f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(columns)});"
    if conn is None:
        with get_db() as conn:
            c = conn.cursor()
            c.execute(create_stmt)
            conn.commit()
    else:
        c = conn.cursor()
        c.execute(create_stmt)

_db_initialized = False
_db_init_lock = threading.Lock()

def get_db():
    conn = sqlite3.connect(DB_FILE, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    return conn
    
# add_test_user()

def migrate_remove_country_column():
    with get_db() as conn:
        c = conn.cursor()
        # Check if country column exists
        c.execute("PRAGMA table_info(user)")
        columns = [row["name"] for row in c.fetchall()]
        if "country" not in columns:
            return  # No migration needed
        # Create new table without country column
        c.execute("""
            CREATE TABLE IF NOT EXISTS user_new (
                uid INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                phone TEXT,
                create_date TEXT DEFAULT CURRENT_TIMESTAMP,
                write_date TEXT
            )
        """)
        # Copy data excluding country
        c.execute("""
            INSERT INTO user_new (uid, name, email, password, phone, create_date, write_date)
            SELECT uid, name, email, password, phone, create_date, write_date FROM user
        """)
        # Drop old table
        c.execute("DROP TABLE user")
        # Rename new table
        c.execute("ALTER TABLE user_new RENAME TO user")
        conn.commit()
        
def ensure_db_initialized():
    global _db_initialized
    if _db_initialized:
        return
    with _db_init_lock:
        if _db_initialized:
            return
        if not os.path.exists(DB_FILE):
            init_db()
        retries = 5
        delay = 0.5
        for attempt in range(retries):
            try:
                with get_db() as conn:
                    c = conn.cursor()
                    c.execute("PRAGMA table_info(submissions)")
                    existing = {row["name"] for row in c.fetchall()}
                    for col in ["user", "form_title", "submitted_at", "form_description", "form_structure", "logo_data"]:
                        if col not in existing:
                            c.execute(f"ALTER TABLE submissions ADD COLUMN {col} TEXT")
                    c.execute("PRAGMA table_info(user)")
                    user_existing = {row["name"] for row in c.fetchall()}
                    for col in ["phone", "write_date"]:
                        if col not in user_existing:
                            c.execute(f"ALTER TABLE user ADD COLUMN {col} TEXT")
                    # Perform migration to remove 'country' column
                    c.execute("PRAGMA foreign_keys=off;")
                    c.execute("""
                        CREATE TABLE IF NOT EXISTS user_new (
                            uid INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                            name TEXT NOT NULL,
                            email TEXT UNIQUE NOT NULL,
                            password TEXT NOT NULL,
                            phone TEXT,
                            create_date TEXT DEFAULT CURRENT_TIMESTAMP,
                            write_date TEXT
                        );
                    """)
                    c.execute("""
                        INSERT INTO user_new (uid, name, email, password, phone, create_date, write_date)
                        SELECT uid, name, email, password, phone, create_date, write_date FROM user;
                    """)
                    c.execute("DROP TABLE user;")
                    c.execute("ALTER TABLE user_new RENAME TO user;")
                    c.execute("PRAGMA foreign_keys=on;")
                    conn.commit()
                _db_initialized = True
                
                #add_test_user()
                break
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e):
                    time.sleep(delay)
                else:
                    raise
        else:
            raise sqlite3.OperationalError("Database is locked after multiple retries")
                            
                 
# -----------------------------------------------------------------------------
# Route: Create Form (Save definition + create response table)
# -----------------------------------------------------------------------------
@app.route("/create_form", methods=["POST"])
def create_form():
    # Retrieve form data from POST request
    form_fields = json.loads(request.form.get("form_fields", "[]"))
    form_title = request.form.get("form_title", "").strip()
    form_description = request.form.get("form_description", "").strip()
    user = request.form.get("user_name", "Anonymous")
    access = request.form.get("access", "private")
    logo_data = request.form.get("logo_data", "")

    # Remove debug flash message for create_form received form_title
    # flash(f"Debug: create_form received form_title = {form_title}", "info")

    if not form_fields:
        flash("Cannot create a form without any fields.", "danger")
        return redirect(url_for("allforms_view"))

    if not form_title:
        form_title = "Untitled Form"

    submitted_at = datetime.now().isoformat()
    structure_json = json.dumps(form_fields)

    store = {
        "user": user,
        "form_title": form_title,
        "form_description": form_description,
        "form_structure": structure_json,
        "submitted_at": submitted_at,
        "access": access,
        "logo_data": logo_data
    }

    cols = ",".join(store.keys())
    placeholders = ",".join("?" for _ in store)
    vals = list(store.values())

    with get_db() as conn:
        c = conn.cursor()
        c.execute(f"INSERT INTO submissions ({cols}) VALUES ({placeholders})", vals)
        form_id = c.lastrowid
        conn.commit()

        create_dynamic_table(form_id, form_fields, conn=conn)
    # Removed success flash message to avoid alert
    # flash("Form created successfully!", "success")
    return redirect(url_for("formmaker_view", form_id=form_id))
        
# -----------------------------------------------------------------------------
# Navbar Injection
# -----------------------------------------------------------------------------
@app.context_processor
def inject_navbar():
    username = session.get("username", "Guest")
    navbar = f'''
    <nav class="navbar navbar-expand-lg navbar-light bg-white shadow-sm" style="position:sticky;top:0;z-index:100;">
      <div class="container-fluid">
        <a class="navbar-brand fw-bold text-primary" href="{url_for('home')}">
          <img src="{url_for('static', filename='logo.png')}" alt="Logo" style="height:36px;vertical-align:middle;margin-right:8px;">
          Form Builder Pro
        </a>
        <div class="d-flex align-items-center ms-auto">
          <a href="{url_for('reset')}" class="btn btn-warning me-2">Form Builder</a>
          <a href="{url_for('home')}" class="btn btn-warning me-2">Home</a>
          <a href="{url_for('allforms_view')}" class="btn btn-warning me-2">View All Forms</a>
          <a href="{url_for('viewuser')}" class="btn btn-warning me-2">View Users</a>
          {'<div class="dropdown ms-3">' if session.get('logged_in') else ''}
          {'<button class="btn btn-light rounded-circle d-flex align-items-center profile-icon" type="button" id="profileDropdown" data-bs-toggle="dropdown" aria-expanded="false" style="box-shadow:0 2px 8px rgba(0,0,0,0.08);">' if session.get('logged_in') else ''}
          {f'<span class="me-2 fw-semibold text-primary">{username[0].upper()}</span>' if session.get('logged_in') else ''}
          {'</button>' if session.get('logged_in') else ''}
          {'<ul class="dropdown-menu dropdown-menu-end" aria-labelledby="profileDropdown">' if session.get('logged_in') else ''}
          {f'<li><span class="dropdown-item-text">Hi, {username}</span></li>' if session.get('logged_in') else ''}
          {'<li><a class="dropdown-item" href="' + url_for('viewuser') + '">Profile</a></li>' if session.get('logged_in') else ''}
          {'<li><hr class="dropdown-divider"></li>' if session.get('logged_in') else ''}
          {'<li><a class="dropdown-item" href="' + url_for('logout') + '">Sign out</a></li>' if session.get('logged_in') else ''}
          {'</ul>' if session.get('logged_in') else ''}
          {'</div>' if session.get('logged_in') else ''}
          {f'<a href="{url_for("login")}" class="btn btn-light rounded-pill px-4 fw-semibold ms-3" style="box-shadow:0 2px 8px rgba(0,0,0,0.08);"><i class="bi bi-person-circle me-2"></i>Login</a>' if not session.get('logged_in') else ''}
        </div>
      </div>
    </nav>
       
    <style>
      .dark-mode {{
        background-color: #181a1b !important;
        color: #e0e0e0 !important;
      }}
      .dark-mode .navbar {{
        background-color: #23272b !important;
      }}
      .dark-mode .card, .dark-mode .modal-content, .dark-mode .table {{
        background-color: #23272b !important;
        color: #e0e0e0 !important;
      }}
      .dark-mode .btn-warning {{
        background-color: #444 !important;
        color: #ffd600 !important;
        border: none;
      }}
      .dark-mode .btn-dark {{
        background-color: #ffd600 !important;
        color: #23272b !important;
      }}
      .dark-mode .form-control {{
        background-color: #23272b !important;
        color: #e0e0e0 !important;
        border-color: #444 !important;
      }}
      .dark-mode .table-light {{
        background-color: #23272b !important;
        color: #e0e0e0 !important;
      }}
      .dark-mode .alert {{
        background-color: #23272b !important;
        color: #ffd600 !important;
        border-color: #ffd600 !important;
      }}
    </style>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/bootstrap-icons.css">
    '''
    return dict(navbar=navbar)
    # -----------------------------------------------------------------------------
# Form Builder (Session-backed)
# -----------------------------------------------------------------------------

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

@app.route("/login", methods=["GET", "POST"])
def login():
    print(f"DEBUG: Request method: {request.method}")
    print(f"DEBUG: Form data: {request.form}")
    uid = request.args.get("uid")
    user = None
    if uid is not None:
        try:
            uid = int(uid)
        except ValueError:
            uid = None
    with get_db() as conn:
        c = conn.cursor()
        if uid:
            c.execute("SELECT * FROM user WHERE uid=?", (uid,))
            user = c.fetchone()

    if request.method == "GET":
        # Render login page with user data if uid provided
        return render_template("login.html", user=user)

    # POST request handling
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "").strip()
    
    # Authentication logic here (simplified example)
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM user WHERE LOWER(TRIM(email))=?", (email.lower(),))
        user = c.fetchone()
    if not user:
        print(f"DEBUG: No user found with email {email}")
        flash("Email not registered. Please register first.", "warning")
        return render_template("login.html", user=None)
    stored_password = user["password"].strip()
    print(f"DEBUG: Stored password: {repr(stored_password)}, Input password: {repr(password)}")
    if stored_password != password:
        print("DEBUG: Password mismatch")
        flash("Invalid email or password.", "danger")
        return render_template("login.html", user=None)
        
    # On successful login, set session and redirect
    session["logged_in"] = True
    session["user_id"] = user["uid"]
    session["username"] = user["name"]
    flash("Logged in successfully.", "success")
    return redirect(url_for("home"))
                
                
                        
@app.route("/logout")
def logout():
   session.clear()
   flash("Logged out successfully.", "info")
   return redirect(url_for("home"))
    #
@app.route("/", methods=["GET", "POST"])
def root_redirect():
    return redirect(url_for("home"))

from datetime import datetime

@app.route("/home", methods=["GET"])
def home():
    user_id = session.get("user_id")
    recent_forms = []
    with get_db() as conn:
        c = conn.cursor()
        if user_id:
            c.execute("SELECT id, form_title, submitted_at FROM submissions WHERE user = (SELECT name FROM user WHERE uid=?) ORDER BY submitted_at DESC LIMIT 3", (user_id,))
        else:
            c.execute("SELECT id, form_title, submitted_at FROM submissions WHERE access='public' ORDER BY submitted_at DESC LIMIT 3")
        rows = c.fetchall()
        for row in rows:
            recent_forms.append({
                "id": row["id"],
                "title": row["form_title"],
                "last_edited": row["submitted_at"]
            })
    return render_template("home.html", now=datetime.now, recent_forms=recent_forms)
            
@app.route("/edit_form/<int:form_id>")
def edit_form(form_id):
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT form_structure, form_title, form_description, logo_data FROM submissions WHERE id=?", (form_id,))
        row = c.fetchone()
        if not row:
            flash("Form not found.", "danger")
            return redirect(url_for("home"))
        try:
            form_fields = json.loads(row["form_structure"])
        except Exception:
            form_fields = []
        session["form_fields"] = form_fields
        session["form_title"] = row["form_title"]
        session["form_description"] = row["form_description"]
        session["logo_data"] = row["logo_data"]
    return redirect(url_for("firstpage"))
                
# Predefined templates with fields
TEMPLATES = {
    "school_admission": {
        "title": "School Admission Form",
        "description": "Collect student details for school admissions.",
        "fields": [
            {"label": "Name of pupil (In capital letters)", "name": "name_of_pupil", "type": "text", "required": "required"},
            {"label": "Admission sought for Class", "name": "admission_class", "type": "text", "required": "required"},
            {"label": "Academic Year", "name": "academic_year", "type": "text", "required": "required"},
            {"label": "Date of Birth", "name": "dob", "type": "dob", "required": "required"},
            {"label": "Aadhar No.", "name": "aadhar_no", "type": "text", "required": ""},
            {"label": "Place of Birth", "name": "place_of_birth", "type": "text", "required": ""},
            {"label": "State", "name": "state", "type": "text", "required": ""},
            {"label": "Nationality", "name": "nationality", "type": "text", "required": ""},
            {"label": "Religion", "name": "religion", "type": "text", "required": ""},
            {"label": "Gender", "name": "gender", "type": "radio", "options": ["Male", "Female"], "required": "required"},
            {"label": "Caste", "name": "caste", "type": "text", "required": ""},
            {"label": "Residential Address", "name": "residential_address", "type": "textarea", "required": ""},
            {"label": "Pin Code", "name": "pin_code", "type": "text", "required": ""},
            {"label": "Mother Tongue", "name": "mother_tongue", "type": "text", "required": ""},
            {"label": "Blood Group", "name": "blood_group", "type": "text", "required": ""},
            {"label": "Identification Mark 1", "name": "identification_mark_1", "type": "text", "required": ""},
            {"label": "Identification Mark 2", "name": "identification_mark_2", "type": "text", "required": ""},
            {"label": "Previous School Name & Location", "name": "previous_school_name_location", "type": "text", "required": ""},
            {"label": "Class", "name": "previous_class", "type": "text", "required": ""},
            {"label": "Year of Study", "name": "previous_year_of_study", "type": "text", "required": ""},
            {"label": "Percentage/Grade", "name": "previous_percentage_grade", "type": "text", "required": ""},
            {"label": "Appraisal of your Child", "name": "appraisal", "type": "textarea", "required": ""},
            {"label": "General Behaviour", "name": "general_behaviour", "type": "checkbox", "options": ["Mild", "Normal", "Hyperactive"], "required": ""},
            {"label": "History of illness, allergy or physical/psychological illness", "name": "history_illness", "type": "textarea", "required": ""},
            {"label": "Second language in previous class", "name": "second_language_previous_class", "type": "text", "required": ""},
            {"label": "Third language in previous class", "name": "third_language_previous_class", "type": "text", "required": ""},
            {"label": "Language preference (From Standard V)", "name": "language_preference", "type": "text", "required": ""},
            {"label": "Second language", "name": "second_language", "type": "checkbox", "options": ["Telugu", "Hindi"], "required": ""},
            {"label": "Third language", "name": "third_language", "type": "checkbox", "options": ["Telugu", "Hindi"], "required": ""}
        ]
    },
    "college_registration": {
        "title": "College Registration",
        "description": "Easy registration for college events or admissions.",
        "fields": [
            {"label": "First Name", "name": "first_name", "type": "text", "required": "required"},
            {"label": "Last Name", "name": "last_name", "type": "text", "required": "required"},
            {"label": "Email", "name": "email", "type": "text", "required": "required"},
            {"label": "Phone Number", "name": "phone_number", "type": "text", "required": ""}
        ]
    },
    "cricket_tournament": {
        "title": "Cricket Tournament",
        "description": "Register teams and players for cricket events.",
        "fields": [
            {"label": "Team Name", "name": "team_name", "type": "text", "required": "required"},
            {"label": "Captain Name", "name": "captain_name", "type": "text", "required": "required"},
            {"label": "Email", "name": "email", "type": "text", "required": "required"},
            {"label": "Phone Number", "name": "phone_number", "type": "text", "required": ""}
        ]
    },
    "job_application": {
        "title": "Job Application",
        "description": "Collect job applications and resumes easily.",
        "fields": [
            {"label": "Full Name", "name": "full_name", "type": "text", "required": "required"},
            {"label": "Email", "name": "email", "type": "text", "required": "required"},
            {"label": "Phone Number", "name": "phone_number", "type": "text", "required": ""},
            {"label": "Resume Link", "name": "resume_link", "type": "text", "required": ""}
        ]
    },
    "feedback_form": {
        "title": "Feedback Form",
        "description": "Gather feedback from users or customers.",
        "fields": [
            {"label": "Name", "name": "name", "type": "text", "required": ""},
            {"label": "Email", "name": "email", "type": "text", "required": ""},
            {"label": "Feedback", "name": "feedback", "type": "text", "required": "required"}
        ]
    },
    "event_rsvp": {
        "title": "Event RSVP",
        "description": "Let guests RSVP for your events online.",
        "fields": [
            {"label": "Name", "name": "name", "type": "text", "required": "required"},
            {"label": "Email", "name": "email", "type": "text", "required": "required"},
            {"label": "Phone Number", "name": "phone_number", "type": "text", "required": ""}
        ]
    },
    "create_your_own": {
        "title": "Create Your Own",
        "description": "Start from scratch and build a fully custom form for any purpose.",
        "fields": []
    }
}

@app.route("/load_template/<template_name>")
@login_required
def load_template(template_name):
    template = TEMPLATES.get(template_name)
    if not template:
        flash("Template not found.", "danger")
        return redirect(url_for("home"))
    session["form_fields"] = template["fields"]
    session["form_title"] = template["title"]
    session["form_description"] = template["description"]
    return redirect(url_for("firstpage"))
        
@app.route("/register", methods=["GET", "POST"])
def register():
    uid = request.args.get("uid")
    user = None
    if uid is not None:
        try:
            uid = int(uid)
        except ValueError:
            uid = None
    with get_db() as conn:
        c = conn.cursor()
        if uid:
            c.execute("SELECT * FROM user WHERE uid=?", (uid,))
            user = c.fetchone()

    if request.method == "GET":
        # Render register page with user data if uid provided
        return render_template("register.html", user=user)

    # POST request handling
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")
    phone = request.form.get("phone", "")
    form_uid = request.form.get("uid")
    if form_uid is not None:
        try:
            form_uid = int(form_uid)
        except ValueError:
            form_uid = None

    if form_uid:
        # Update existing user
        normalized_email = email.lower()
        c.execute("SELECT * FROM user WHERE LOWER(TRIM(email))=? AND uid!=?", (normalized_email, form_uid))
        existing_user = c.fetchone()
        if existing_user:
            flash("Email already registered. Please login.", "warning")
            return render_template("register.html", user=user)

        # Handle password change with current password verification
        current_password = request.form.get("current_password", "")
        if current_password:
            c.execute("SELECT password FROM user WHERE uid=?", (form_uid,))
            row = c.fetchone()
            if not row or row["password"] != current_password:
                flash("Current password is incorrect.", "danger")
                # Return register page with user data without redirect
                return render_template("register.html", user=user)
    
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")
        if new_password or confirm_password:
            if not (new_password and confirm_password):
                flash("New password and confirmation are required.", "danger")
                return render_template("register.html", user=user)
            if new_password != confirm_password:
                flash("New password and confirmation do not match.", "danger")
                return render_template("register.html", user=user)
            password_to_set = new_password
        else:
            password_to_set = password

        try:
            c.execute("UPDATE user SET name=?, email=?, password=?, phone=?, write_date=? WHERE uid=?", (name, email, password_to_set, phone, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), form_uid))
            conn.commit()
            flash("User updated successfully.", "success")
            return redirect(url_for("viewuser"))
        except Exception as e:
            flash("Error updating user.", "danger")
            return render_template("register.html", user=user)
    else:
        # Registration: only check email uniqueness, then create user
        c.execute("SELECT * FROM user WHERE LOWER(TRIM(email))=?", (email.lower(),))
        existing_user = c.fetchone()
        if existing_user:
            flash("Email already registered. Please login.", "warning")
            return render_template("register.html")
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c.execute("INSERT INTO user (name, email, password, phone, create_date, write_date) VALUES (?, ?, ?, ?, ?, ?)", (name, email, password.strip(), phone, now, now))
            conn.commit()
            flash("User created successfully.", "success")
            return redirect(url_for("login"))
        except Exception as e:
            flash("Error creating new user.", "danger")
            return render_template("register.html")
                
@app.route("/firstpage", methods=["GET", "POST"])
@login_required
def firstpage():
    
    form_fields = session.get("form_fields", [])
    edit_index = request.args.get("edit")
    editing = None
    if edit_index and edit_index.isdigit():
        idx = int(edit_index)
        if 0 <= idx < len(form_fields):
            editing = form_fields[idx]

    if request.method == "POST":
        form_title = request.form.get("form_title", "").strip()
        if not form_title:
            form_title = "Untitled Form"
        # Keep only debug flash message for firstpage received form_title
        flash(f"Debug: firstpage received form_title = {form_title}", "info")
        session["form_title"] = form_title
        session["user_name"]  = request.form.get("user_name", "Anonymous")
        session["form_description"] = request.form.get("form_description", "")
        print(f"DEBUG: form_title to be sent: {form_title}")

        # Read edit_index from form data on POST
        edit_index = request.form.get("edit_index")
        submit_action = request.form.get("submit_action")

        new_field = {
            "label": request.form.get("label", ""),
            "name":  request.form.get("name", "").strip().replace(" ", "_"),
            "type":  request.form.get("type", "text"),
            "placeholder": request.form.get("placeholder", ""),
            "value": request.form.get("value", ""),
            "description": request.form.get("description", ""),
            "required": "required" if request.form.get("required") else "",
            "options": []
        }

        if new_field["type"] == "number":
            new_field["min"] = request.form.get("min", "")
            new_field["max"] = request.form.get("max", "")
        else:
            new_field["minlength"] = request.form.get("minlength", "")
            new_field["maxlength"] = request.form.get("maxlength", "")

        if new_field["type"] in ("radio", "checkbox", "select"):
            opts = request.form.get("options", "")
            new_field["options"] = [o.strip() for o in opts.split(",") if o.strip()]

        # Check for duplicate label or name
        duplicate_label = any(f["label"] == new_field["label"] for f in form_fields)
        duplicate_name = any(f["name"] == new_field["name"] for f in form_fields)

        if submit_action == "delete_field" and edit_index is not None and edit_index.isdigit():
            idx = int(edit_index)
            print(f"DEBUG: Attempting to delete field at index {idx} from form_fields with length {len(form_fields)}")
            if 0 <= idx < len(form_fields):
                form_fields.pop(idx)
                session["form_fields"] = form_fields
                print(f"DEBUG: Field deleted successfully. Updated form_fields length: {len(form_fields)}")
                flash("Field deleted successfully.", "success")
            else:
                print(f"DEBUG: Invalid field index for deletion: {idx}")
                flash("Invalid field index for deletion.", "danger")
        elif duplicate_label or duplicate_name:
            flash("Duplicate label or field name is not allowed.", "danger")
        else:
            if edit_index is not None and edit_index.isdigit():
                idx = int(edit_index)
                if 0 <= idx < len(form_fields):
                    # Update the existing field with new_field data
                    form_fields[idx].update(new_field)
            else:
                form_fields.append(new_field)

        session["form_fields"] = form_fields

        # Redirect to /firstpage after update to clear edit query param
        return redirect(url_for("firstpage"))

    # For GET requests, render the firstpage.html template
    return render_template(
        "firstpage.html",
        editing_field=editing,
        form_fields=form_fields,
        title=session.get("form_title", ""),
        form_description=session.get("form_description", "")
    )
                    
from flask import request, jsonify

@app.route('/reorder_session_fields', methods=['POST'])
def reorder_session_fields():
    order = request.json.get('order', [])
    form_fields = session.get('form_fields', [])
    # Reorder form_fields according to the new order
    try:
        new_fields = [form_fields[int(i)] for i in order]
        session['form_fields'] = new_fields
        return jsonify(status='success')
    except Exception as e:
        return jsonify(status='error', message=str(e)), 400


# -----------------------------------------------------------------------------
# Form Live Preview
# -----------------------------------------------------------------------------
@app.route("/formmaker", methods=["GET", "POST"], endpoint="formmaker_view")
def formmaker_page():
    form_id = request.args.get("form_id", default=0, type=int)
    shared = request.args.get("shared", default="0")
    # Removed debug flash messages for cleaner UI
    if form_id:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT form_title, form_description, form_structure FROM submissions WHERE id=?", (form_id,))
            row = c.fetchone()
        if row:
            try:
                form_fields = json.loads(row["form_structure"])
            except Exception as e:
                form_fields = []
            title = row["form_title"]
            description = row["form_description"]
        else:
            form_fields = []
            title = "Untitled Form"
            description = "Live Preview of Your Form"
    else:
        # During form building (unsaved state)
        form_fields = session.get("form_fields", [])
        title = session.get("form_title", "Untitled Form")
        description = session.get("form_description", "Live Preview of Your Form")

    if shared == "1":
        # For shared link, load form fields from DB but do not use session data
        # So do nothing here, keep form_fields loaded from DB
        # Optionally, disable editing features in template using shared flag
        # Also, disable navbar to prevent navigation
        navbar = ""
    else:
        navbar = '''
        <nav class="navbar navbar-expand-lg navbar-light bg-light mb-4">
          <div class="container d-flex align-items-center justify-content-between">
            <div class="d-flex align-items-center">
              <div style="width: 40px; height: 40px; background-color: #6a5acd; color: white; font-weight: bold; font-size: 1.5rem; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin-right: 10px;">
                {{ session.get('username', 'G')[0].upper() }}
              </div>
              <span class="me-3">Welcome, {{ session.get('username', 'Guest') }}</span>
            </div>
            <div>
              <a href="{{ url_for('reset') }}" class="btn btn-warning me-2">Form Builder</a>
              <a href="{{ url_for('home') }}" class="btn btn-warning me-2">Home</a>
              <a href="{{ url_for('allforms_view') }}" class="btn btn-warning me-2">View All Forms</a>
              <a href="{{ url_for('viewuser') }}" class="btn btn-warning me-2">View Users</a>
            </div>
          </div>
        </nav>
        '''
    
    return render_template("formmaker.html",
                           title=title,
                           description=description,
                           form_fields=form_fields,
                           form_id=form_id,
                           shared=shared,
                           navbar=navbar)

@app.route('/delete_session_field/<int:index>', methods=['POST'])
def delete_session_field(index):
    form_fields = session.get('form_fields', [])
    if 0 <= index < len(form_fields):
        form_fields.pop(index)
        session['form_fields'] = form_fields
        return jsonify({'status': 'success'})
    else:
        return jsonify({'status': 'error', 'message': 'Invalid field index'})
            

# -----------------------------------------------------------------------------
# Dynamic Submission Endpoint (Inserts into dynamic table)
# -----------------------------------------------------------------------------
@app.route("/submit_form", methods=["POST"], endpoint="submit_form_v1")
def submit_form():
    form_structure = json.loads(request.form.get("form_structure", "[]"))
    form_id = int(request.form.get("form_id", 0))

    # Removed debug flash message

    # Server-side input validation
    errors = []
    for field in form_structure:
        fname = field.get("name")
        value = request.form.get(fname, "")
        # Required
        if field.get("required") and not value:
            errors.append(f"{field.get('label', fname)} is required.")
        # Min/Max Length
        if field.get("minlength") and len(value) < int(field["minlength"]):
            errors.append(f"{field.get('label', fname)} must be at least {field['minlength']} characters.")
        if field.get("maxlength") and len(value) > int(field["maxlength"]):
            errors.append(f"{field.get('label', fname)} must be at most {field['maxlength']} characters.")
        # Min/Max Value for numbers
        if field.get("type") == "number":
            try:
                num = float(value)
                if field.get("min") and num < float(field["min"]):
                    errors.append(f"{field.get('label', fname)} must be at least {field['min']}.")
                if field.get("max") and num > float(field["max"]):
                    errors.append(f"{field.get('label', fname)} must be at most {field['max']}.")
            except ValueError:
                errors.append(f"{field.get('label', fname)} must be a number.")

    if errors:
        for error in errors:
            flash(error, "danger")
        return redirect(request.referrer or url_for('formmaker_view', form_id=form_id))

    data = request.form.to_dict(flat=False)  # get all values as lists
    form_title = request.form.get("form_title", "Untitled Form")
    shared = request.form.get("shared", "0")
    if shared == "1":
        user = "Shared User"
    else:
        user = request.form.get("user", "Anonymous")
        form_description = request.form.get("form_description", "")

    # Removed debug flash messages

    field_names = [field.get("name") for field in form_structure if "name" in field]

    filtered_dynamic_fields = {}

    for field in form_structure:
        fname = field.get("name")
        if fname and fname in data:
            if field.get("type") == "checkbox":
                # Join multiple checkbox values as comma-separated string
                values = data.get(fname, [])
                if isinstance(values, list):
                    filtered_dynamic_fields[fname] = ",".join(values)
                else:
                    filtered_dynamic_fields[fname] = values
            else:
                # For other fields, take the first value
                val = data.get(fname)
                if isinstance(val, list):
                    filtered_dynamic_fields[fname] = val[0]
                else:
                    filtered_dynamic_fields[fname] = val

    if form_id == 0:
        flash("Invalid form ID.", "danger")
        return redirect(url_for("allforms_view"))

    # Use a separate connection for create_dynamic_table to avoid locking
    with get_db() as conn:
        create_dynamic_table(form_id, form_structure, conn=conn)

        c = conn.cursor()

        # Insert into dynamic response table
        table_name = f"form_{form_id}_responses"
        columns = ", ".join(f'"{col}"' for col in filtered_dynamic_fields.keys())
        placeholders = ", ".join("?" for _ in filtered_dynamic_fields)
        values = list(filtered_dynamic_fields.values())

        # Removed debug flash message

        c.execute(f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})", values)

        conn.commit()

    flash("Form submitted successfully!", "success")
    shared = request.form.get("shared", "0")
    if shared == "1":
        # Render submission success page with fill again button for shared forms
        submitted_data = {k: v[0] if isinstance(v, list) else v for k, v in filtered_dynamic_fields.items()}
        return render_template("submit.html",
                               title=form_title,
                               submitted=submitted_data,
                               shared=shared)
    else:
        return redirect(url_for("formmaker_view", form_id=form_id))
                    
# -----------------------------------------------------------------------------
# View Single Response
# -----------------------------------------------------------------------------
@app.route("/view_response/<int:form_id>/<int:response_id>")
def view_response(form_id, response_id):
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT form_title, form_structure FROM submissions WHERE id=?", (form_id,))
        form_row = c.fetchone()
    if not form_row:
        flash("Form not found", "warning")
        return redirect(url_for("allforms_view"))
    form_title = form_row["form_title"]
    try:
        form_fields = json.loads(form_row["form_structure"])
    except Exception as e:
        form_fields = []
    
    init_response_table(form_id)
    table_name = f"form_{form_id}_responses"
    with get_db() as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute(f"SELECT * FROM {table_name} WHERE id=?", (response_id,))
        response_row = c.fetchone()
    if not response_row:
        flash("Response not found", "danger")
        return redirect(url_for("allforms_view"))
    response_data = dict(response_row)
    return render_template("view_response.html",
                           form_title=form_title,
                           form_id=form_id,
                           response_id=response_id,
                           form_fields=form_fields,
                           response_data=response_data,
                           messages=get_flashed_messages(with_categories=True))

# -----------------------------------------------------------------------------
# Edit Submission
# -----------------------------------------------------------------------------
@app.route("/edit_submission/<int:form_id>/<int:response_id>", methods=["GET", "POST"])
def edit_submission(form_id, response_id):
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT form_title, form_structure FROM submissions WHERE id=?", (form_id,))
        form_row = c.fetchone()
    if not form_row:
        flash("Form not found", "warning")
        return redirect(url_for("allforms_view"))
    form_title = form_row["form_title"]
    try:
        form_fields = json.loads(form_row["form_structure"])
    except Exception:
        form_fields = []

    init_response_table(form_id)
    table_name = f"form_{form_id}_responses"
    with get_db() as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute(f"SELECT * FROM {table_name} WHERE id=?", (response_id,))
        response_row = c.fetchone()
    if not response_row:
        flash("Response not found", "danger")
        return redirect(url_for("allforms_view"))
    response_data = dict(response_row)

    if request.method == "POST":
        # Process form submission update
        updated_data = {}
        for field in form_fields:
            fname = field.get("name")
            if not fname:
                continue
            if field.get("type") == "checkbox":
                values = request.form.getlist(fname)
                updated_data[fname] = ",".join(values)
            else:
                updated_data[fname] = request.form.get(fname, "")
        # Update the dynamic response table
        with get_db() as conn:
            c = conn.cursor()
            set_clause = ", ".join(f'"{k}" = ?' for k in updated_data.keys())
            values = list(updated_data.values())
            values.append(response_id)
            c.execute(f"UPDATE {table_name} SET {set_clause} WHERE id = ?", values)
            conn.commit()
        flash("Submission updated successfully.", "success")
        return redirect(url_for("view_response", form_id=form_id, response_id=response_id))

    # For GET request, render the edit form template
    return render_template("edit_form.html",
                           form_title=form_title,
                           form_id=form_id,
                           allowed_fields=form_fields,
                           submission_dict=response_data,
                           response_id=response_id)
                
# -----------------------------------------------------------------------------
# View All Responses for a Form
# -----------------------------------------------------------------------------
@app.route("/view_all_responses/<int:form_id>")
def view_all_responses(form_id):
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT form_title, form_structure FROM submissions WHERE id=?", (form_id,))
        form_row = c.fetchone()
    if not form_row:
        flash("Form not found.", "danger")
        return redirect(url_for("allforms_view"))
    form_title = form_row["form_title"]
    try:
        form_fields = json.loads(form_row["form_structure"])
    except Exception as e:
        form_fields = []
    table_name = f"form_{form_id}_responses"
    with get_db() as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute(f"SELECT * FROM {table_name} ORDER BY submitted_at DESC")
        responses = c.fetchall()
    return render_template("view_all_responses.html",
                           form_title=form_title,
                           form_id=form_id,
                           form_fields=form_fields,
                           responses=responses,
                           messages=get_flashed_messages(with_categories=True))

# -----------------------------------------------------------------------------
# View Layout of a Form
# -----------------------------------------------------------------------------
@app.route("/view_layout/<int:form_id>", methods=["GET", "POST"])
def view_layout(form_id):
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT form_title, form_description, form_structure FROM submissions WHERE id=?", (form_id,))
        form_row = c.fetchone()
    if not form_row:
        flash("Form not found.", "danger")
        return redirect(url_for("allforms_view"))
    form_title = form_row["form_title"]
    form_description = form_row["form_description"]
    try:
        form_fields = json.loads(form_row["form_structure"])
    except Exception:
        form_fields = []

    if request.method == "POST":
        # Handle form layout edits here (e.g., add/edit/delete fields)
        # For now, just flash a message and redirect back
        flash("Edit Layout functionality is not yet implemented.", "info")
        return redirect(url_for("view_layout", form_id=form_id))

    return render_template("view_layout.html",
                           form_title=form_title,
                           form_description=form_description,
                           form_structure=form_fields,
                           form_id=form_id)

# -----------------------------------------------------------------------------
# Edit Layout of a Form
# -----------------------------------------------------------------------------
@app.route("/edit_layout/<int:form_id>", methods=["GET", "POST"])
def edit_layout(form_id):
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT form_title, form_description, form_structure FROM submissions WHERE id=?", (form_id,))
        form_row = c.fetchone()
    if not form_row:
        flash("Form not found.", "danger")
        return redirect(url_for("allforms_view"))
    form_title = form_row["form_title"]
    form_description = form_row["form_description"]
    try:
        form_fields = json.loads(form_row["form_structure"])
    except Exception:
        form_fields = []

    editing_field = None
    edit_index = request.args.get("edit")
    if edit_index is not None and edit_index.isdigit():
        idx = int(edit_index)
        if 0 <= idx < len(form_fields):
            editing_field = form_fields[idx]
            

    if request.method == "POST":
        form_fields = form_fields or []
        # Get form data
        form_title = request.form.get("form_title", form_title).strip()
        form_description = request.form.get("form_description", form_description).strip()
        edit_index = request.form.get("edit_index")
        submit_action = request.form.get("submit_action")

        # Handle delete action
        if submit_action == "delete_field" and edit_index is not None:
            try:
                idx = int(edit_index)
                if 0 <= idx < len(form_fields):
                    form_fields.pop(idx)
                    flash("Field deleted successfully.", "success")
                    # Save changes immediately after deletion
                    c.execute("UPDATE submissions SET form_structure=? WHERE id=?", (json.dumps(form_fields), form_id))
                    conn.commit()
                else:
                    flash("Invalid field index for deletion.", "danger")
            except Exception:
                flash("Error deleting field.", "danger")
            
        # Handle add or update field
        elif submit_action in ("add_field", "save_all", None):
            # Extract field data from form
            label = request.form.get("label", "").strip()
            name = request.form.get("name", "").strip().replace(" ", "_")
            field_type = request.form.get("type", "text")
            placeholder = request.form.get("placeholder", "")
            value = request.form.get("value", "")
            description = request.form.get("description", "")
            required = "required" if request.form.get("required") else ""
            options_raw = request.form.get("options", "")
            options = [o.strip() for o in options_raw.split(",") if o.strip()] if field_type in ("radio", "checkbox", "select") else []

            # Validation: check for duplicate label or name
            duplicate_label = any(f["label"] == label for f in form_fields)
            duplicate_name = any(f["name"] == name for f in form_fields)

            new_field = {
                "label": label,
                "name": name,
                "type": field_type,
                "placeholder": placeholder,
                "value": value,
                "description": description,
                "required": required,
                "options": options
            }

            if field_type == "number":
                new_field["min"] = request.form.get("min", "")
                new_field["max"] = request.form.get("max", "")
            else:
                new_field["minlength"] = request.form.get("minlength", "")
                new_field["maxlength"] = request.form.get("maxlength", "")

            if duplicate_label or duplicate_name:
                flash("Duplicate label or field name is not allowed.", "danger")
            else:
                if edit_index is not None and edit_index.isdigit():
                    idx = int(edit_index)
                    if 0 <= idx < len(form_fields):
                        form_fields[idx] = new_field
                        flash("Field updated successfully.", "success")
                    else:
                        flash("Invalid field index for update.", "danger")
                else:
                    form_fields.append(new_field)
                    flash("Field added successfully.", "success")

        # Save all changes to DB if save_all action
        if submit_action == "save_all":
            try:
                with get_db() as conn:
                    c = conn.cursor()
                    c.execute("UPDATE submissions SET form_title=?, form_description=?, form_structure=? WHERE id=?",
                              (form_title, form_description, json.dumps(form_fields), form_id))
                    conn.commit()
                flash("Form layout saved successfully.", "success")
            except Exception as e:
                flash(f"Error saving form layout: {e}", "danger")

        # Update local variables for rendering
        form_title = form_title
        form_description = form_description

        return render_template("edit_layout.html",
                               title=form_title,
                               form_description=form_description,
                               form_fields=form_fields,
                               form_id=form_id,
                               editing_field=editing_field,
                               edit_index=edit_index)
                        
    return render_template("edit_layout.html",
                           title=form_title,
                           form_description=form_description,
                           form_fields=form_fields,
                           form_id=form_id,
                           editing_field=editing_field,
                           edit_index=edit_index)
# -----------------------------------------------------------------------------
# Edit Submission (Edit a response for a form)
# -----------------------------------------------------------------------------
# Removed duplicate edit_submission function to fix route conflict
                    
# -----------------------------------------------------------------------------
# List All Forms (Form Definitions)
# -----------------------------------------------------------------------------
@app.route("/allforms", endpoint="allforms_view")
def allforms():
    filtered_forms = []
    logged_in_user = session.get("username", "Guest")
    user_id = session.get("user_id")
    is_admin = False
    with get_db() as conn:
        c = conn.cursor()
        if user_id:
            c.execute("SELECT is_admin FROM user WHERE uid=?", (user_id,))
            row = c.fetchone()
            if row and row["is_admin"]:
                is_admin = True
        c.execute("SELECT id, user, form_title, form_description, form_structure, access FROM submissions ORDER BY submitted_at DESC")
        rows = c.fetchall()
        for row in rows:
            try:
                form_structure = json.loads(row["form_structure"])
                # Filter forms based on access level and logged-in user or admin
                if is_admin or row["access"] == "public" or (row["access"] == "private" and row["user"] == logged_in_user):
                    filtered_forms.append({
                        "id": row["id"],
                        "user": row["user"],
                        "form_title": row["form_title"],
                        "form_description": row["form_description"],
                        "access": row["access"]
                    })
            except Exception:
                # If JSON parsing fails, still include the form if access allows
                if is_admin or row["access"] == "public" or (row["access"] == "private" and row["user"] == logged_in_user):
                    filtered_forms.append({
                        "id": row["id"],
                        "user": row["user"],
                        "form_title": row["form_title"],
                        "form_description": row["form_description"],
                        "access": row["access"]
                    })
    return render_template("allforms.html", forms=filtered_forms, logged_in_user=logged_in_user)

@app.route('/update_access/<int:form_id>', methods=['POST'])
def update_access(form_id):
    data = request.get_json()
    new_access = data.get('access')
    if new_access not in ['public', 'private']:
        return {'status': 'error', 'message': 'Invalid access level'}, 400

    user_id = session.get('user_id')
    if not user_id:
        return {'status': 'error', 'message': 'Unauthorized'}, 401

    with get_db() as conn:
        c = conn.cursor()
        # Check if user is admin or owner of the form
        c.execute("SELECT user FROM submissions WHERE id=?", (form_id,))
        row = c.fetchone()
        if not row:
            return {'status': 'error', 'message': 'Form not found'}, 404
        form_owner = row['user']

        c.execute("SELECT is_admin FROM user WHERE uid=?", (user_id,))
        user_row = c.fetchone()
        is_admin = user_row and user_row['is_admin']

        if not is_admin and form_owner != session.get('username'):
            return {'status': 'error', 'message': 'Permission denied'}, 403

        # Update access level
        c.execute("UPDATE submissions SET access=? WHERE id=?", (new_access, form_id))
        conn.commit()

    return {'status': 'success'}
                    
# -----------------------------------------------------------------------------
# View and Manage Users (CRUD)
# -----------------------------------------------------------------------------
@app.route("/viewuser")
def viewuser():
    user_id = session.get("user_id")
    if not user_id:
        flash("User not logged in.", "danger")
        return redirect(url_for("login"))
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT is_admin FROM user WHERE uid=?", (user_id,))
        row = c.fetchone()
        if not row:
            flash("User not found.", "danger")
            return redirect(url_for("login"))
        is_admin = row["is_admin"]
        if is_admin:
            # Admin: fetch all users including the current admin user
            c.execute("SELECT uid, name, email, password, phone, create_date, write_date FROM user ORDER BY create_date DESC")
            users = c.fetchall()
            users_list = []
            for user in users:
                user_dict = {k: user[k] for k in user.keys()}  # Convert sqlite3.Row to dict with string keys
                if not user_dict.get("name") or user_dict.get("name").strip() == "":
                    user_dict["name"] = "N/A"
                phone = user_dict.get("phone", "")
                country = (user_dict.get("country") or "").lower()
                country_code_map = {
                    "indian": "+91",
                    "india": "+91",
                    "usa": "+1",
                    "united states": "+1",
                    "uk": "+44",
                    "united kingdom": "+44",
                    "canada": "+1",
                    "australia": "+61",
                    "germany": "+49",
                    "france": "+33",
                    "japan": "+81",
                    "china": "+86"
                }
                code = country_code_map.get(country, "")
                if phone and code and not phone.startswith(code):
                    digits = ''.join(filter(str.isdigit, phone))
                    digits = digits[:10]
                    phone = f"{code} {digits}"
                    user_dict["phone"] = phone
                users_list.append(user_dict)
            return render_template("viewuser.html", users=users_list)
        else:
            # Normal user: fetch only own data
            c.execute("SELECT uid, name, email, password, phone, create_date, write_date FROM user WHERE uid=?", (user_id,))
            user = c.fetchone()
            if not user:
                flash("User not found.", "danger")
                return redirect(url_for("login"))
            user_dict = {k: user[k] for k in user.keys()}
            if not user_dict.get("name") or user_dict.get("name").strip() == "":
                user_dict["name"] = "N/A"
            phone = user_dict.get("phone", "")
            country = (user_dict.get("country") or "").lower()
            country_code_map = {
                "indian": "+91",
                "india": "+91",
                "usa": "+1",
                "united states": "+1",
                "uk": "+44",
                "united kingdom": "+44",
                "canada": "+1",
                "australia": "+61",
                "germany": "+49",
                "france": "+33",
                "japan": "+81",
                "china": "+86"
            }
            code = country_code_map.get(country, "")
            if phone and code and not phone.startswith(code):
                digits = ''.join(filter(str.isdigit, phone))
                digits = digits[:10]
                phone = f"{code} {digits}"
                user_dict["phone"] = phone
            return render_template("viewuser.html", users=[user_dict])
                    
@app.route("/add_user", methods=["POST"])
def add_user():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "").strip()
    if not (name and email and password):
        flash("All fields are required to add a user.", "danger")
        return redirect(url_for("viewuser"))
    with get_db() as conn:
        c = conn.cursor()
        try:
            c.execute("INSERT INTO user (name, email, password, create_date) VALUES (?, ?, ?, ?)",
                      (name, email, password, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
            flash("User added successfully.", "success")
        except sqlite3.IntegrityError:
            flash("Email already exists.", "danger")
    return redirect(url_for("viewuser"))

@app.route("/edit_user/<int:uid>", methods=["POST"])
def edit_user(uid):
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "").strip()
    if not (name and email and password):
        flash("All fields are required to update a user.", "danger")
    
    with get_db() as conn:
        c = conn.cursor()
        try:
            c.execute("UPDATE user SET name=?, email=?, password=? WHERE uid=?", (name, email, password, uid))
            conn.commit()
            flash("User updated successfully.", "success")
        except sqlite3.IntegrityError:
            flash("Email already exists.", "danger")
    return redirect(url_for("viewuser"))

import time

@app.route("/delete_user/<int:uid>", methods=["POST"])
def delete_user(uid):
    retries = 2
    delay = 0.1
    for attempt in range(retries):
        try:
            with get_db() as conn:
                c = conn.cursor()
                c.execute("DELETE FROM user WHERE uid=?", (uid,))
                conn.commit()
            flash("User deleted successfully.", "success")
            break
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e):
                time.sleep(delay)
            else:
                raise
    else:
        flash("Failed to delete user due to database lock. Please try again.", "danger")
    return redirect(url_for("viewuser"))
                
@app.route("/change_password/<int:uid>", methods=["POST"])
def change_password(uid):
    current_password = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not (current_password and new_password and confirm_password):
        flash("All password fields are required.", "danger")
        return redirect(url_for("viewuser"))

    if new_password != confirm_password:
        flash("New password and confirmation do not match.", "danger")
        return redirect(url_for("viewuser"))

    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT password FROM user WHERE uid=?", (uid,))
        row = c.fetchone()
        if not row:
            return redirect(url_for("viewuser"))
        stored_password = row["password"]
        if current_password != stored_password:
            flash("Current password is incorrect.", "danger")
            return redirect(url_for("viewuser"))
        try:
            c.execute("UPDATE user SET password=? WHERE uid=?", (new_password, uid))
            conn.commit()
            flash("Password updated successfully.", "success")
        except Exception as e:
            flash(f"Error updating password: {e}", "danger")
    return redirect(url_for("viewuser"))

@app.route("/verify_password/<int:uid>", methods=["POST"])
def verify_password(uid):
    data = request.get_json()
    current_password = data.get("current_password", "")
    if not current_password:
        return {"success": False, "message": "Current password is required."}, 400
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT password FROM user WHERE uid=?", (uid,))
        row = c.fetchone()
        if not row:
            return {"success": False, "message": "User not found."}, 404
        stored_password = row["password"]
        if current_password == stored_password:
            return {"success": True, "message": "Password verified."}
        else:
            return {"success": False, "message": "Current password is incorrect."}, 401
            
@app.route("/edit_user_info/<int:uid>", methods=["GET", "POST"])
def edit_user_info(uid):
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT uid, name, email, phone, password FROM user WHERE uid=?", (uid,))
        user = c.fetchone()
        if not user:
            flash("User not found.", "danger")
            return redirect(url_for("viewuser"))
        user = dict(user)
        
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not name or not email:
            flash("Name and email are required.", "danger")
            return render_template("edit_user_info.html", user=user)

        # If any password fields are filled, validate current password and new passwords
        if current_password or new_password or confirm_password:
            if not (current_password and new_password and confirm_password):
                flash("All password fields are required for password change.", "danger")
                return render_template("edit_user_info.html", user=user)
            if new_password != confirm_password:
                flash("New password and confirmation do not match.", "danger")
                return render_template("edit_user_info.html", user=user)
            # Verify current password
            if current_password != user.get("password", ""):
                flash("Current password is incorrect.", "danger")
                return render_template("edit_user_info.html", user=user)

        with get_db() as conn:
            c = conn.cursor()
            # Check if email is already registered to another user
            print(f"Debug edit_user_info route: Checking email uniqueness for email: '{email.lower().strip()}', uid: {uid}")
            c.execute("SELECT uid FROM user WHERE LOWER(TRIM(email))=? AND uid!=?", (email.lower().strip(), uid))
            existing_user = c.fetchone()
            print(f"Debug edit_user_info route: existing_user found: {existing_user}")
            if existing_user:
                flash("Email already registered. Please use a different email.", "warning")
                return render_template("edit_user_info.html", user=user)
            try:
                if new_password:
                    c.execute("UPDATE user SET name=?, email=?, phone=?, password=? WHERE uid=?", (name, email, phone, new_password, uid))
                else:
                    c.execute("UPDATE user SET name=?, email=?, phone=? WHERE uid=?", (name, email, phone, uid))
                conn.commit()
                flash("User updated successfully.", "success")
                # Update session username if the edited user is the logged-in user
                if session.get("logged_in") and session.get("username") != name and session.get("email") == email:
                    session["username"] = name
                return redirect(url_for("viewuser"))
            except Exception as e:
                flash(f"Error updating user: {e}", "danger")
                return render_template("edit_user_info.html", user=user)
                    
    return render_template("edit_user_info.html", user=user)
                    
def update_user_name(uid, new_name):
    """Update the name of a user by uid."""
    with get_db() as conn:
        c = conn.cursor()
        c.execute("UPDATE user SET name=? WHERE uid=?", (new_name, uid))
        conn.commit()
                    
@app.route("/statistics/<int:form_id>", methods=["GET"], endpoint="statistics")
def statistics(form_id):
    with get_db() as conn:
        c = conn.cursor()
        # Get form title and structure
        c.execute("SELECT form_title, form_structure FROM submissions WHERE id=?", (form_id,))
        row = c.fetchone()
        if not row:
            flash("Form not found.", "danger")
            return redirect(url_for("allforms_view"))
        form_title = row["form_title"]
        try:
            form_structure = json.loads(row["form_structure"])
        except Exception:
            form_structure = []
        number_of_fields = len(form_structure)

        # Count total submissions from dynamic response table
        table_name = f"form_{form_id}_responses"
        try:
            c.execute(f"SELECT COUNT(*) as total FROM {table_name}")
            total_submissions = c.fetchone()["total"]
        except Exception:
            total_submissions = 0

        # Aggregate priority counts
        priority_counts = {"High": 0, "Medium": 0, "Low": 0}
        try:
            c.execute(f"SELECT data FROM {table_name}")
            rows = c.fetchall()
            for row in rows:
                data_json = row["data"]
                try:
                    data = json.loads(data_json)
                    priority = data.get("priority", "").capitalize()
                    if priority in priority_counts:
                        priority_counts[priority] += 1
                except Exception:
                    continue
        except Exception:
            pass

        # Aggregate status counts
        status_categories = ["Open", "In Progress", "Confirmed", "Cancelled"]
        status_counts = {status: 0 for status in status_categories}
        try:
            c.execute(f"SELECT data FROM {table_name}")
            rows = c.fetchall()
            for row in rows:
                data_json = row["data"]
                try:
                    data = json.loads(data_json)
                    status = data.get("status", "").title()
                    if status in status_counts:
                        status_counts[status] += 1
                except Exception:
                    continue
        except Exception:
            pass

        total_status = sum(status_counts.values())
        if total_status > 0:
            status_open_percent = round(status_counts["Open"] / total_status * 100, 1)
            status_in_progress_percent = round(status_counts["In Progress"] / total_status * 100, 1)
            status_confirmed_percent = round(status_counts["Confirmed"] / total_status * 100, 1)
            status_cancelled_percent = round(status_counts["Cancelled"] / total_status * 100, 1)
        else:
            status_open_percent = 0
            status_in_progress_percent = 0
            status_confirmed_percent = 0
            status_cancelled_percent = 0

        # Example: get counts for a select/radio field called 'country'
        c.execute("SELECT form_structure FROM submissions WHERE id=?", (form_id,))
        row = c.fetchone()
        form_structure = json.loads(row['form_structure'])
        field_names = [f['name'] for f in form_structure if f['type'] in ['select', 'radio', 'checkbox']]
        chart_data = {}
        for fname in field_names:
            c.execute(f"SELECT {fname} FROM 'form_{form_id}_responses'")
            values = [r[fname] for r in c.fetchall()]
            counts = {}
            for v in values:
                for val in (v.split(',') if ',' in v else [v]):
                    counts[val] = counts.get(val, 0) + 1
            chart_data[fname] = counts
            
        stats = {
            "total_submissions": total_submissions,
            "number_of_fields": number_of_fields,
            "priority_high": priority_counts["High"],
            "priority_medium": priority_counts["Medium"],
            "priority_low": priority_counts["Low"],
            "status_open": status_counts["Open"],
            "status_in_progress": status_counts["In Progress"],
            "status_confirmed": status_counts["Confirmed"],
            "status_cancelled": status_counts["Cancelled"],
            "status_open_percent": status_open_percent,
            "status_in_progress_percent": status_in_progress_percent,
            "status_confirmed_percent": status_confirmed_percent,
            "status_cancelled_percent": status_cancelled_percent
        }

    return render_template("statistics.html",
                           form_id=form_id,
                           form_title=form_title,
                           stats=stats,
                           chart_data=json.dumps(chart_data))
@app.route("/delete_confirmation/<int:form_id>", methods=["GET"], endpoint="delete_confirmation")
def delete_confirmation(form_id):
    # Render a confirmation page for deleting a form
    return render_template("delete.html", form_id=form_id)

@app.route("/delete_form/<int:form_id>", methods=["POST"], endpoint="delete_form")
def delete_form(form_id):
    with get_db() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM submissions WHERE id=?", (form_id,))
        c.execute(f"DROP TABLE IF EXISTS form_{form_id}_responses")
        conn.commit()
    flash("Form deleted successfully.", "success")
    return redirect(url_for("allforms_view"))
    
@app.route('/export_csv/<int:form_id>')
def export_csv(form_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT form_title, form_structure FROM submissions WHERE id=?", (form_id,))
    row = c.fetchone()
    if not row:
        return "Form not found", 404
    form_structure = json.loads(row['form_structure'])
    field_names = [field['name'] for field in form_structure if 'name' in field]

    # Get all responses for this form
    try:
        c.execute(f"SELECT {', '.join(field_names)} FROM 'form_{form_id}_responses'")
        responses = c.fetchall()
    except Exception as e:
        return f"Error fetching responses: {str(e)}", 500

    def generate():
        import io
        si = io.StringIO()
        writer = csv.writer(si)
        writer.writerow(field_names)
        for resp in responses:
            writer.writerow([resp[field] for field in field_names])
        output = si.getvalue()
        si.close()
        return output

    csv_data = generate()
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename=form_{form_id}_responses.csv"}
    )

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)