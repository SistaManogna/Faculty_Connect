from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'faculty_connect_secret_2024')

DATABASE = '/tmp/faculty_connect.db'

DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']

PERIODS = {
    1: '8:00 – 8:50 AM',
    2: '8:50 – 9:40 AM',
    3: '9:40 – 10:30 AM',
    4: '10:45 – 11:35 AM',
    5: '11:35 AM – 12:25 PM',
    6: '1:15 – 2:05 PM',
    7: '2:05 – 2:55 PM',
    8: '2:55 – 3:45 PM',
}

PERIOD_RANGES = {
    1:  (8*60,      8*60+50),
    2:  (8*60+50,   9*60+40),
    3:  (9*60+40,   10*60+30),
    4:  (10*60+45,  11*60+35),
    5:  (11*60+35,  12*60+25),
    6:  (13*60+15,  14*60+5),
    7:  (14*60+5,   14*60+55),
    8:  (14*60+55,  15*60+45),
}


# ──────────────────────────────────────────────
# DB helpers
# ──────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            email         TEXT    UNIQUE NOT NULL,
            password_hash TEXT    NOT NULL,
            name          TEXT    NOT NULL,
            role          TEXT    NOT NULL CHECK(role IN ('faculty','student')),
            department    TEXT    DEFAULT '',
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS timetable (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            faculty_id INTEGER NOT NULL,
            day        TEXT    NOT NULL,
            period     INTEGER NOT NULL,
            subject    TEXT    DEFAULT '',
            room       TEXT    DEFAULT '',
            FOREIGN KEY (faculty_id) REFERENCES users(id),
            UNIQUE(faculty_id, day, period)
        );

        CREATE TABLE IF NOT EXISTS faculty_status (
            faculty_id  INTEGER PRIMARY KEY,
            status      TEXT NOT NULL DEFAULT 'available'
                            CHECK(status IN ('available','busy','leave')),
            updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (faculty_id) REFERENCES users(id)
        );
    ''')
    conn.close()


# ──────────────────────────────────────────────
# Decorators
# ──────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to continue.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


# ──────────────────────────────────────────────
# Time helpers
# ──────────────────────────────────────────────

def get_current_period():
    now = datetime.now()
    t = now.hour * 60 + now.minute
    for period, (start, end) in PERIOD_RANGES.items():
        if start <= t <= end:
            return period
    return None


def get_current_day():
    d = datetime.now().weekday()   # 0 = Monday … 5 = Saturday, 6 = Sunday
    return DAYS[d] if d < 6 else None


# ──────────────────────────────────────────────
# Auth routes
# ──────────────────────────────────────────────

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('faculty_dashboard') if session['role'] == 'faculty' else url_for('student_dashboard'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        db   = get_db()
        user = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        db.close()

        if user and check_password_hash(user['password_hash'], password):
            session.update({'user_id': user['id'], 'name': user['name'],
                            'role': user['role'], 'email': user['email']})
            return redirect(url_for('faculty_dashboard') if user['role'] == 'faculty' else url_for('student_dashboard'))

        flash('Invalid email or password.', 'danger')

    return render_template('login.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if 'user_id' in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        name       = request.form.get('name', '').strip()
        email      = request.form.get('email', '').strip().lower()
        password   = request.form.get('password', '')
        role       = request.form.get('role', 'student')
        department = request.form.get('department', '').strip()

        if not all([name, email, password]):
            flash('All fields are required.', 'danger')
            return render_template('signup.html')

        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'danger')
            return render_template('signup.html')

        db = get_db()
        try:
            db.execute(
                'INSERT INTO users (email, password_hash, name, role, department) VALUES (?,?,?,?,?)',
                (email, generate_password_hash(password), name, role, department)
            )
            db.commit()
            flash('Account created! Please log in.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('An account with this email already exists.', 'danger')
        finally:
            db.close()

    return render_template('signup.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


# ──────────────────────────────────────────────
# Faculty routes
# ──────────────────────────────────────────────

@app.route('/faculty/dashboard')
@login_required
def faculty_dashboard():
    if session['role'] != 'faculty':
        return redirect(url_for('student_dashboard'))

    db = get_db()
    rows = db.execute(
        'SELECT day, period, subject, room FROM timetable WHERE faculty_id = ?',
        (session['user_id'],)
    ).fetchall()

    timetable = {}
    for r in rows:
        timetable[(r['day'], r['period'])] = {'subject': r['subject'], 'room': r['room']}

    status_row = db.execute(
        'SELECT status FROM faculty_status WHERE faculty_id = ?', (session['user_id'],)
    ).fetchone()
    current_status = status_row['status'] if status_row else 'available'
    db.close()

    current_day    = get_current_day()
    current_period = get_current_period()

    current_slot = None
    if current_day and current_period:
        entry = timetable.get((current_day, current_period))
        if entry and (entry['subject'] or entry['room']):
            current_slot = entry

    # Serialise for JS
    tt_json = {f"{day}_{period}": v for (day, period), v in timetable.items()}

    return render_template('faculty_dashboard.html',
        timetable=timetable,
        tt_json=tt_json,
        days=DAYS,
        periods=PERIODS,
        current_status=current_status,
        current_day=current_day,
        current_period=current_period,
        current_slot=current_slot,
        has_timetable=bool(rows),
    )


@app.route('/faculty/timetable', methods=['POST'])
@login_required
def save_timetable_cell():
    if session['role'] != 'faculty':
        return jsonify({'error': 'Unauthorized'}), 403

    data    = request.get_json()
    day     = data.get('day', '')
    period  = int(data.get('period', 0))
    subject = data.get('subject', '').strip()
    room    = data.get('room', '').strip()

    if day not in DAYS or period not in PERIODS:
        return jsonify({'error': 'Invalid day or period'}), 400

    db = get_db()
    db.execute('''
        INSERT INTO timetable (faculty_id, day, period, subject, room)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(faculty_id, day, period)
        DO UPDATE SET subject = excluded.subject, room = excluded.room
    ''', (session['user_id'], day, period, subject, room))
    db.commit()
    db.close()

    return jsonify({'success': True})


@app.route('/faculty/status', methods=['POST'])
@login_required
def update_status():
    if session['role'] != 'faculty':
        return jsonify({'error': 'Unauthorized'}), 403

    status = request.get_json().get('status', '')
    if status not in ('available', 'busy', 'leave'):
        return jsonify({'error': 'Invalid status'}), 400

    db = get_db()
    db.execute('''
        INSERT INTO faculty_status (faculty_id, status, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(faculty_id)
        DO UPDATE SET status = excluded.status, updated_at = excluded.updated_at
    ''', (session['user_id'], status))
    db.commit()
    db.close()

    return jsonify({'success': True, 'status': status})


# ──────────────────────────────────────────────
# Student routes
# ──────────────────────────────────────────────

@app.route('/student/dashboard')
@login_required
def student_dashboard():
    if session['role'] != 'student':
        return redirect(url_for('faculty_dashboard'))

    return render_template('student_dashboard.html',
        days=DAYS,
        periods=PERIODS,
        current_day=get_current_day(),
        current_period=get_current_period(),
    )


@app.route('/api/search')
@login_required
def search_faculty():
    name   = request.args.get('name', '').strip()
    day    = request.args.get('day', '').strip()
    period = request.args.get('period', '').strip()

    if not name:
        return jsonify({'error': 'Name is required'}), 400

    try:
        period = int(period) if period else None
    except ValueError:
        return jsonify({'error': 'Invalid period'}), 400

    db = get_db()
    results = db.execute('''
        SELECT u.id, u.name, u.department,
               t.subject, t.room,
               COALESCE(fs.status, 'available') AS status
        FROM   users u
        LEFT JOIN timetable t
               ON t.faculty_id = u.id AND t.day = ? AND t.period = ?
        LEFT JOIN faculty_status fs ON fs.faculty_id = u.id
        WHERE  u.role = 'faculty' AND u.name LIKE ?
        ORDER  BY u.name
    ''', (day, period, f'%{name}%')).fetchall()
    db.close()

    data = [{
        'name':       r['name'],
        'department': r['department'] or 'N/A',
        'subject':    r['subject']    or '—',
        'room':       r['room']       or '—',
        'status':     r['status'],
    } for r in results]

    return jsonify({'results': data})


@app.route('/api/faculty-names')
@login_required
def faculty_names():
    q = request.args.get('q', '').strip()
    db = get_db()
    rows = db.execute(
        'SELECT DISTINCT name FROM users WHERE role = "faculty" AND name LIKE ? LIMIT 10',
        (f'%{q}%',)
    ).fetchall()
    db.close()
    return jsonify({'names': [r['name'] for r in rows]})


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)
