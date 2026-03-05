import csv
from flask import Response, session
from flask import Flask, render_template, request, redirect
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3

app = Flask(__name__)

app.secret_key = "supersecretkey"

def init_db():
    conn = sqlite3.connect("students.db")
    cursor = conn.cursor()

    # Students table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        roll INTEGER NOT NULL,
        attendance REAL NOT NULL,
        user_id INTEGER,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)

    # Subjects table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS subjects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject_name TEXT UNIQUE NOT NULL
    )
    """)

    # Marks table (Bridge table)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS marks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER,
        subject_id INTEGER,
        marks REAL,
        FOREIGN KEY(student_id) REFERENCES students(id),
        FOREIGN KEY(subject_id) REFERENCES subjects(id)
    )
    """)

    conn.commit()
    conn.close()

init_db()   

def create_user_table():
    conn = sqlite3.connect("students.db")
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT
        )
    """)

    conn.commit()
    conn.close()

create_user_table()

def insert_default_subjects():
    conn = sqlite3.connect("students.db")
    cursor = conn.cursor()

    subjects = ["Maths", "Science", "English"]

    for subject in subjects:
        try:
            cursor.execute("INSERT INTO subjects (subject_name) VALUES (?)", (subject,))
        except:
            pass

    conn.commit()
    conn.close()

insert_default_subjects()

def calculate_risk(attendance, avg):

    # Academic Risk
    if avg >= 75:
        academic_risk = "Low"
    elif avg >= 50:
        academic_risk = "Medium"
    else:
        academic_risk = "High"

    # Attendance Risk
    if attendance >= 80:
        attendance_risk = "Low"
    elif attendance >= 65:
        attendance_risk = "Medium"
    else:
        attendance_risk = "High"

    # Overall Risk (Priority: High > Medium > Low)
    if academic_risk == "High" or attendance_risk == "High":
        overall_risk = "High"
    elif academic_risk == "Medium" or attendance_risk == "Medium":
        overall_risk = "Medium"
    else:
        overall_risk = "Low"

    return academic_risk, attendance_risk, overall_risk


# Home Page
@app.route("/")
def home():
    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect("students.db")
    cursor = conn.cursor()

    cursor.execute("""
    SELECT 
        students.id,
        students.name,
        students.roll,
        students.attendance,
        AVG(marks.marks)
    FROM students
    LEFT JOIN marks ON students.id = marks.student_id
    WHERE students.user_id = ?
    GROUP BY students.id
    """, (session["user_id"],))

    rows = cursor.fetchall()

    students = []

    for row in rows:
        student_id, name, roll, attendance, average = row
        if average is None:
            average = 0

        academic_risk, attendance_risk, overall_risk = calculate_risk(attendance, average)

        students.append((
            student_id,
            name,
            roll,
            attendance,
            round(average, 2),
            academic_risk,
            attendance_risk,
            overall_risk
        ))

    total = len(students)
    high = sum(1 for s in students if s[7] == "High")
    medium = sum(1 for s in students if s[7] == "Medium")
    low = sum(1 for s in students if s[7] == "Low")

    conn.close()

    return render_template(
        "index.html",
        students=students,
        total=total,
        high=high,
        medium=medium,
        low=low
    )


# Show Add Student Form
@app.route("/add")
def add_form():

    if "user_id" not in session:
        return redirect("/login")
    
    conn = sqlite3.connect("students.db")
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM subjects")
    subjects = cursor.fetchall()

    conn.close()

    return render_template("add_student.html", subjects=subjects)


# Handle Form Submission
@app.route("/add_student", methods=["POST"])
def add_student():

    if "user_id" not in session:
        return redirect("/login")

    name = request.form["name"]
    roll = request.form["roll"]
    attendance = float(request.form["attendance"])

    conn = sqlite3.connect("students.db")
    cursor = conn.cursor()

    # Insert student first
    try:
        user_id = session["user_id"]

        cursor.execute("""
            INSERT INTO students (name, roll, attendance, user_id)
            VALUES (?, ?, ?, ?)
            """, (name, roll, attendance, user_id))

        student_id = cursor.lastrowid

    except sqlite3.IntegrityError:
        conn.close()
        return "Roll number already exists!"


    # Fetch all subjects
    cursor.execute("SELECT * FROM subjects")
    subjects = cursor.fetchall()

    total_marks = 0

    for subject in subjects:
        subject_id = subject[0]
        mark = float(request.form[f"subject_{subject_id}"])

        total_marks += mark

        cursor.execute("""
            INSERT INTO marks (student_id, subject_id, marks)
            VALUES (?, ?, ?)
        """, (student_id, subject_id, mark))

    average = total_marks / len(subjects)

    # Calculate risk
    academic_risk, attendance_risk, overall_risk = calculate_risk(attendance, average)

    conn.commit()
    conn.close()

    return redirect("/students")

@app.route("/students")
def view_students():

    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect("students.db")
    cursor = conn.cursor()

    cursor.execute("""
    SELECT 
        students.id,
        students.name,
        students.roll,
        students.attendance,
        AVG(marks.marks)
    FROM students
    LEFT JOIN marks ON students.id = marks.student_id
    WHERE students.user_id = ?
    GROUP BY students.id
    """, (session["user_id"],))

    rows = cursor.fetchall()

    risk_filter = request.args.get("risk")

    students = []

    for row in rows:
        student_id, name, roll, attendance, average = row

        if average is None:
            average = 0

        academic_risk, attendance_risk, overall_risk = calculate_risk(attendance, average)

        student_data = (
            student_id,
            name,
            roll,
            attendance,
            round(average, 2),
            academic_risk,
            attendance_risk,
            overall_risk
        )

        # Apply filter here
        if risk_filter:
            if overall_risk == risk_filter:
                students.append(student_data)
        else:
            students.append(student_data)

    # Statistics
    total = len(students)
    high = sum(1 for s in students if s[7] == "High")
    medium = sum(1 for s in students if s[7] == "Medium")
    low = sum(1 for s in students if s[7] == "Low")

    conn.close()

    return render_template(
    "students.html",
    students=students,
    total=total,
    high=high,
    medium=medium,
    low=low
   )

@app.route("/export")
def export_csv():

    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect("students.db")
    cursor = conn.cursor()

    cursor.execute("""
    SELECT 
        students.id,
        students.name,
        students.roll,
        students.attendance,
        AVG(marks.marks)
    FROM students
    LEFT JOIN marks ON students.id = marks.student_id
    WHERE students.user_id = ?
    GROUP BY students.id
    """, (session["user_id"],))

    rows = cursor.fetchall()

    output = []

    # CSV Header
    output.append([
        "Name",
        "Roll",
        "Attendance (%)",
        "Average",
        "Academic Risk",
        "Attendance Risk",
        "Overall Risk"
    ])

    for row in rows:
        student_id, name, roll, attendance, average = row

        if average is None:
            average = 0

        academic_risk, attendance_risk, overall_risk = calculate_risk(attendance, average)

        output.append([
            name,
            roll,
            attendance,
            round(average, 2),
            academic_risk,
            attendance_risk,
            overall_risk
        ])

    conn.close()

    def generate():
        for row in output:
            yield ",".join(map(str, row)) + "\n"

    return Response(
        generate(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=students_report.csv"}
    )

@app.route("/delete/<int:id>")
def delete_student(id):

    if "user_id" not in session:
        return redirect("/login")
    
    conn = sqlite3.connect("students.db")
    cursor = conn.cursor()

    cursor.execute("DELETE FROM marks WHERE student_id = ?", (id,))
    cursor.execute("DELETE FROM students WHERE id = ? AND user_id = ?", (id, session["user_id"]))

    conn.commit()
    conn.close()

    return redirect("/students")   

@app.route("/edit/<int:id>")
def edit_student(id):

    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect("students.db")
    cursor = conn.cursor()

    # Get student basic info
    cursor.execute("SELECT * FROM students WHERE id = ? AND user_id = ?", (id, session["user_id"]))
    student = cursor.fetchone()

    # Get all subjects
    cursor.execute("SELECT * FROM subjects")
    subjects = cursor.fetchall()

    # Get student marks
    cursor.execute("""
        SELECT subject_id, marks
        FROM marks
        WHERE student_id = ?
    """, (id,))

    marks_data = cursor.fetchall()

    # Convert marks to dictionary
    marks_dict = {subject_id: marks for subject_id, marks in marks_data}

    conn.close()

    return render_template(
        "edit_student.html",
        student=student,
        subjects=subjects,
        marks_dict=marks_dict
    )

@app.route("/update/<int:id>", methods=["POST"])
def update_student(id):

    if "user_id" not in session:
        return redirect("/login")

    name = request.form["name"]
    roll = request.form["roll"]
    attendance = float(request.form["attendance"])

    conn = sqlite3.connect("students.db")
    cursor = conn.cursor()

    # Update student info
    cursor.execute("""
        UPDATE students
        SET name = ?, roll = ?, attendance = ?
        WHERE id = ? AND user_id = ?
    """, (name, roll, attendance, id, session["user_id"]))

    # Get all subjects
    cursor.execute("SELECT * FROM subjects")
    subjects = cursor.fetchall()

    for subject in subjects:
        subject_id = subject[0]
        mark = float(request.form[f"subject_{subject_id}"])

        # Check if mark already exists
        cursor.execute("""
            SELECT id FROM marks
            WHERE student_id = ? AND subject_id = ?
        """, (id, subject_id))

        existing = cursor.fetchone()

        if existing:
            # Update
            cursor.execute("""
                UPDATE marks
                SET marks = ?
                WHERE student_id = ? AND subject_id = ?
            """, (mark, id, subject_id))
        else:
            # Insert
            cursor.execute("""
                INSERT INTO marks (student_id, subject_id, marks)
                VALUES (?, ?, ?)
            """, (id, subject_id, mark))

    conn.commit()
    conn.close()

    return redirect("/students")

@app.route("/subjects")
def manage_subjects():

    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect("students.db")
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM subjects")
    subjects = cursor.fetchall()

    conn.close()

    return render_template("subjects.html", subjects=subjects)

@app.route("/add_subject", methods=["POST"])
def add_subject():

    subject_name = request.form["subject_name"]

    conn = sqlite3.connect("students.db")
    cursor = conn.cursor()

    try:
        cursor.execute(
            "INSERT INTO subjects (subject_name) VALUES (?)",
            (subject_name,)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        pass  # Ignore duplicate subject

    conn.close()

    return redirect("/subjects")

@app.route("/delete_subject/<int:id>")
def delete_subject(id):

    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect("students.db")
    cursor = conn.cursor()

    cursor.execute("DELETE FROM marks WHERE subject_id = ?", (id,))
    cursor.execute("DELETE FROM subjects WHERE id = ?", (id,))

    conn.commit()
    conn.close()

    return redirect("/subjects")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = generate_password_hash(request.form["password"])

        conn = sqlite3.connect("students.db")
        cursor = conn.cursor()

        try:
            cursor.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (username, password)
            )
            conn.commit()
            conn.close()
            return redirect("/login")
        except:
            return "Username already exists"

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = sqlite3.connect("students.db")
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user[2], password):
            session["user_id"] = user[0]
            session["username"] = username
            return redirect("/")
        else:
            return "Invalid credentials"

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)