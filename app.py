import calendar
from genericpath import exists
from locale import normalize
from click import prompt
from flask import Flask, render_template, request, redirect, session, send_from_directory
from PyPDF2 import PdfReader
import json, sqlite3, os
import pandas as pd
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
import itertools
import google.generativeai as genai

import requests
import os
from dotenv import load_dotenv

load_dotenv()

def send_email(to_email, subject, body):

    url = "https://api.brevo.com/v3/smtp/email"

    headers = {
        "accept": "application/json",
        "api-key": os.getenv("BREVO_API_KEY"),
        "content-type": "application/json"
    }

    data = {
        "sender": {
            "name": "Faculty Recruitment",
            "email": "mohanrajvijayan@msec.edu.in"
        },
        "to": [
            {"email": to_email}
        ],
        "subject": subject,
        "htmlContent": f"<p>{body}</p>"
    }

    response = requests.post(url, json=data, headers=headers)

    print("STATUS:", response.status_code)
    print("RESPONSE:", response.text)

# get keys from env
keys = os.getenv("GEMINI_API_KEYS").split(",")

api_key_cycle = itertools.cycle(keys)

def get_next_api_key():
    return next(api_key_cycle)

def get_client():
    genai.configure(api_key=get_next_api_key())
    return genai

def normalize(score):
    if score is None:
        return 0

    score = float(score)

    if score <= 1:
        score *= 100
    elif score <= 10:
        score *= 10

    return round(score, 2)

# ✅ ADD HERE
def adjust_scores_from_summary(research_score, teaching_score, research_summary, teaching_summary):

    research_summary = research_summary.lower()
    teaching_summary = teaching_summary.lower()

    # -------------------------
    # RESEARCH SCORE FIX
    # -------------------------
    if any(x in research_summary for x in [
        "no research", "not specified", "no publications"
    ]):
        research_score = 10


    elif "ph.d" in research_summary and "no publications" in research_summary:
        research_score = 30

    elif any(x in research_summary for x in [
        "some research", "limited research"
    ]):
        research_score = min(research_score, 50)

    elif any(x in research_summary for x in [
        "strong research", "multiple publications", "extensive research"
    ]):
        research_score = max(research_score, 80)

    # -------------------------
    # TEACHING SCORE FIX
    # -------------------------
    if any(x in teaching_summary for x in [
        "no teaching", "no experience"
    ]):
        teaching_score = 10

    elif any(x in teaching_summary for x in [
        "limited teaching", "basic teaching"
    ]):
        teaching_score = min(teaching_score, 50)

    elif any(x in teaching_summary for x in [
        "strong teaching", "extensive experience", "excellent teaching"
    ]):
        teaching_score = max(teaching_score, 80)

    return research_score, teaching_score


app = Flask(__name__)
app.secret_key = "faculty_recruitment_secret"


def format_time(seconds):
    m = seconds // 60
    s = seconds % 60
    return f"{m}m {s}s"


@app.route("/report/<int:candidate_id>")
def view_report(candidate_id):

    conn = sqlite3.connect("recruitment.db")
    cursor = conn.cursor()

    cursor.execute("""
    SELECT name, email, department, post,
           semantic_score, interview_score,
           psychometric_score, final_score,
           tech_time, psycho_time
    FROM candidates
    WHERE id=?
    """, (candidate_id,))

    data = cursor.fetchone()
    conn.close()

    if not data:
        return "Candidate not found"

    name, email, dept, post, resume_score, tech_score, psycho_score, final_score, tech_time, psycho_time = data

    # format time
    tech_time_fmt = format_time(tech_time or 0)
    psycho_time_fmt = format_time(psycho_time or 0)

    # interpretation logic
    if psycho_score >= 90:
        interpretation = "Highly Suitable for Professor Role"
        bg_color = "#e6f4ea"
        text_color = "#1e7e34"
    elif psycho_score >= 70:
        interpretation = "Suitable with Good Institutional Awareness"
        bg_color = "#e7f6f8"
        text_color = "#117a8b"
    elif psycho_score >= 50:
        interpretation = "Moderately Suitable"
        bg_color = "#fff8e1"
        text_color = "#b8860b"
    elif psycho_score >= 30:
        interpretation = "Low Suitability"
        bg_color = "#fff3e6"
        text_color = "#cc7000"
    else:
        interpretation = "Not Suitable"
        bg_color = "#fdecea"
        text_color = "#b02a37"

    return render_template(
        "report_template.html",
        name=name,
        email=email,
        dept=dept,
        post=post,
        resume_score=resume_score,
        tech_score=tech_score,
        psycho_score=psycho_score,
        final_score=final_score,
        interpretation=interpretation,
        bg_color=bg_color,
        text_color=text_color,
        tech_time=tech_time_fmt,
        psycho_time=psycho_time_fmt
    )
# ---------------------------
# DATABASE INITIALIZATION
# ---------------------------

def init_db():
    conn = sqlite3.connect("recruitment.db")
    print("DATABASE PATH:", os.path.abspath("recruitment.db"))
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS candidates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT,
        phone TEXT,
        gender TEXT,
        department TEXT,
        post TEXT,
        resume_path TEXT,
        semantic_score REAL,
        research_score REAL,
        teaching_score REAL,
        interview_score REAL,
        psychometric_score REAL,
        final_score REAL,
        overall_summary TEXT,
        shortlist TEXT,
        status TEXT,
        created_at TEXT,
        tech_time INTEGER,
        psycho_time INTEGER,
        updated_at TEXT
    )
    """)

    # Questions table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        department TEXT,
        subject TEXT,
        question TEXT,
        option1 TEXT,
        option2 TEXT,
        option3 TEXT,
        option4 TEXT,
        correct_option INTEGER
    )
    """)

    conn.commit()
    conn.close()    

init_db()


# ---------------------------
# HOME
# ---------------------------

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/openings")
def openings():
    return render_template("openings.html")


@app.route("/apply/<dept>")
def apply(dept):

    if dept == "it":
        role_title = "Information Technology Faculty"
        job_description = """
        - PhD/M.E/M.Tech in Information Technology
        - Experience in programming (Python/Java), networking, databases (SQL)
        - Knowledge in Web Technologies, Cloud Computing
        - Teaching experience and research publications preferred
        """

    elif dept == "cse":
        role_title = "Computer Science Faculty"
        job_description = """
        - PhD/M.E/M.Tech in Computer Science
        - Strong knowledge in AI, Machine Learning, Data Science, Cloud Computing
        - Programming skills in Python/Java, Data Structures and Algorithms
        - Teaching experience and research publications preferred
        """

    elif dept == "civil":
        role_title = "Civil Engineering Faculty"
        job_description = """
        - PhD/M.E/M.Tech in Civil Engineering
        - Expertise in Structural Engineering, Geotechnical, Transportation Engineering
        - Knowledge in AutoCAD, Construction Management
        - Teaching experience and research publications preferred
        """

    elif dept == "mech":
        role_title = "Mechanical Engineering Faculty"
        job_description = """
        - PhD/M.E/M.Tech in Mechanical Engineering
        - Knowledge in CAD/CAM, Thermal Engineering, Manufacturing Processes
        - Familiarity with tools like SolidWorks/ANSYS
        - Teaching experience and research publications preferred
        """

    elif dept == "ece":
        role_title = "Electronics & Communication Faculty"
        job_description = """
        - PhD/M.E/M.Tech in Electronics & Communication Engineering
        - Knowledge in VLSI, Embedded Systems, Communication Systems
        - Programming skills in MATLAB, Verilog, or C
        - Teaching experience and research publications preferred
        """

    elif dept == "eee":
        role_title = "Electrical & Electronics Faculty"
        job_description = """
        - PhD/M.E/M.Tech in Electrical Engineering
        - Knowledge in Power Systems, Control Systems, Electrical Machines
        - Familiarity with MATLAB/Simulink
        - Teaching experience preferred
        """

    elif dept == "aids":
        role_title = "Artificial Intelligence & Data Science Faculty"
        job_description = """
        - PhD/M.E/M.Tech in AI, Data Science, or Computer Science
        - Strong knowledge in Machine Learning, Deep Learning, NLP
        - Programming skills in Python, TensorFlow, PyTorch
        - Research publications preferred
        """

    elif dept == "maths":
        role_title = "Mathematics Faculty"
        job_description = """
        - PhD / M.Phil / M.Sc in Mathematics
        - Expertise in Applied Mathematics, Algebra, Statistics
        - Knowledge in Numerical Methods and Data Analysis
        - Teaching experience preferred
        """

    elif dept == "physics":
        role_title = "Physics Faculty"
        job_description = """
        - PhD / M.Phil / M.Sc in Physics
        - Knowledge in Quantum Mechanics, Electromagnetics, Solid State Physics
        - Experience in research and laboratory work preferred
        """

    elif dept == "chemistry":
        role_title = "Chemistry Faculty"
        job_description = """
        - PhD / M.Phil / M.Sc in Chemistry
        - Knowledge in Organic, Inorganic, Physical Chemistry
        - Experience in laboratory techniques and research publications preferred
        """

    else:
        role_title = "Faculty Position"
        job_description = ""

    return render_template(
        "apply.html",
        role_title=role_title,
        job_description=job_description,
        dept=dept
    )
# ---------------------------
# RESUME EVALUATION
# ---------------------------

@app.route("/evaluate", methods=["POST"])
def evaluate():

    name = request.form["name"]
    email = request.form["email"]
    phone = request.form["phone"]
    gender = request.form["gender"]
    post = request.form["post"]
    department = request.form["department"]
    job_description = request.form["job_description"]
    print("JOB DESCRIPTION:", job_description)
    file = request.files["resume"]

    resume_path = f"static/resumes/{name.replace(' ','_')}.pdf"
    file.save(resume_path)

    reader = PdfReader(resume_path)
    resume_text = ""

    for page in reader.pages:
        resume_text += page.extract_text()

    resume_text = resume_text.lower()
    print("RESUME TEXT:", resume_text[:500])
    prompt = f"""
    You are an academic recruitment AI system.

    STRICT RULES:
    - You MUST return ALL fields.
    - Each summary MUST be UNIQUE.
    - DO NOT merge summaries.
    - DO NOT skip any field.
    - If any field is missing, output is INVALID.

    IMPORTANT:
    - Research Summary must ONLY talk about research
    - Teaching Summary must ONLY talk about teaching
    - Overall Summary must be combined evaluation

    Return ONLY valid JSON:

    {{
    "semantic_score": number,
    "research_alignment_score": number,
    "teaching_alignment_score": number,
    "research_summary": "only research related explanation (2 sentences)",
    "teaching_summary": "only teaching related explanation (2 sentences)",
    "overall_summary": "combined final evaluation (3 sentences)",
    "shortlist": "Yes or No"
    }}


    Job Description:
    {job_description}

    Candidate Resume:
    {resume_text}
    """
    client = get_client()

    model = client.GenerativeModel("gemini-pro")

    response = model.generate_content(prompt)

    result_text = response.text

    result_text = response.text.strip()

    if result_text.startswith("```"):
        result_text = result_text.replace("```json", "").replace("```", "").strip()

    try:
        result_json = json.loads(result_text)
    except:
        return f"JSON Parsing Failed <pre>{response.text}</pre>"

    semantic_score = result_json.get("semantic_score")
    research_score = result_json.get("research_alignment_score")
    teaching_score = result_json.get("teaching_alignment_score")

    research_summary = result_json.get("research_summary", "No research details found.")
    teaching_summary = result_json.get("teaching_summary", "No teaching details found.")
    overall_summary = result_json.get("overall_summary", "No overall summary available.")
    shortlist = result_json.get("shortlist")
    print("RAW RESPONSE:", response.text)

    # Insert into DB
    conn = sqlite3.connect("recruitment.db")
    cursor = conn.cursor()
    
    from datetime import datetime
    created_at = datetime.now().strftime("%Y-%m-%d")

    cursor.execute("""
    INSERT INTO candidates
    (name, email, phone, gender, department, post, resume_path,
    semantic_score, research_score, teaching_score, overall_summary,
    shortlist, status, created_at, tech_time, psycho_time, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        name,
        email,
        phone,
        gender,
        department,
        post,
        resume_path,
        semantic_score,
        research_score,
        teaching_score,
        overall_summary,
        shortlist,
        "Pending",
        created_at,
        0,   # tech_time default
        0,   # psycho_time default
        created_at
    ))

    candidate_id = cursor.lastrowid
    conn.commit()
    conn.close()

    # Save data only
    return """
    <script>
    alert("Application submitted successfully!");
    window.location.href = "/openings";
    </script>
    """


# ---------------------------
# DYNAMIC INTERVIEW PAGE
# ---------------------------

@app.route("/psychometric/<int:candidate_id>")
def psychometric(candidate_id):

    conn = sqlite3.connect("recruitment.db")
    cursor = conn.cursor()

    cursor.execute("""
    SELECT question, option1, option2, option3, option4, correct_option
    FROM questions
    WHERE type='psychometric'
    """)

    rows = cursor.fetchall()
    conn.close()

    questions = []
    for r in rows:
        questions.append({
            "question": r[0],
            "options": [r[1], r[2], r[3], r[4]],
            "answer_index": int(r[5])
        })
    return render_template(
        "psychometric.html",
        candidate_id=candidate_id,
        questions=questions
    )

@app.route("/submit_psychometric/<int:candidate_id>", methods=["POST"])
def submit_psychometric(candidate_id):

    # -------------------------
    # FETCH QUESTIONS FROM DB
    # -------------------------
    conn = sqlite3.connect("recruitment.db")
    cursor = conn.cursor()

    cursor.execute("""
    SELECT question, option1, option2, option3, option4, correct_option
    FROM questions
    WHERE type='psychometric'
    """)

    rows = cursor.fetchall()

    # convert to list format
    questions = []
    for r in rows:
        questions.append({
            "question": r[0],
            "options": [r[1], r[2], r[3], r[4]],
            "answer_index": int(r[5])
        })
    # -------------------------
    # VALIDATION
    # -------------------------
    if not questions:
        conn.close()
        return "No psychometric questions found. Please upload."

    # -------------------------
    # CALCULATE SCORE
    # -------------------------
    score = 0

    for i, q in enumerate(questions):
        selected = int(request.form.get(f"q{i}", -1))
        correct = int(q["answer_index"])
        selected = int(request.form.get(f"q{i}", -1))
        if selected == correct:
            score += 5   # correct answer
        elif abs(selected - correct) == 1:
            score += 3   # near answer
        else:
            score += 1   # far answer

    psychometric_score = score
    psycho_time = int(request.form.get("psycho_time", 0))

    # -------------------------
    # UPDATE PSYCHOMETRIC SCORE
    # -------------------------
    cursor.execute("""
    UPDATE candidates
    SET psychometric_score=?, psycho_time=?, updated_at=?
    WHERE id=?
    """, (psychometric_score, psycho_time, datetime.now().strftime("%Y-%m-%d"),candidate_id))

    conn.commit()

    # -------------------------
    # FETCH ALL SCORES
    # -------------------------
    cursor.execute("""
    SELECT semantic_score, interview_score, psychometric_score
    FROM candidates
    WHERE id=?
    """, (candidate_id,))

    data = cursor.fetchone()

    semantic_score = data[0] or 0
    interview_score = data[1] or 0
    psychometric_score = data[2] or 0

    # -------------------------
    # FINAL SCORE
    # -------------------------
    final_score = round(
        0.4 * semantic_score +
        0.4 * interview_score +
        0.2 * psychometric_score, 2
    )

    status = "Selected" if final_score >= 50 else "Rejected"

    cursor.execute("""
    UPDATE candidates
    SET final_score=?, status=?
    WHERE id=?
    """, (final_score, status, candidate_id))

    conn.commit()
    conn.close()

    session.pop("psychometric", None)

    return render_template(
    "results.html",
    candidate_id=candidate_id,
    psychometric_completed=True
    )

# ---------------------------
# ADMIN LOGIN
# ---------------------------

@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if username == "admin" and password == "admin123":
            session["admin_logged_in"] = True
            return redirect("/admin")

        return "Invalid login"

    return render_template("admin_login.html")


# ---------------------------
# ADMIN DASHBOARD
# ---------------------------
@app.route("/admin")
def admin_dashboard():

    if not session.get("admin_logged_in"):
        return redirect("/admin-login")

    conn = sqlite3.connect("recruitment.db")
    cursor = conn.cursor()

    # --------------------
    # FETCH CANDIDATES
    # --------------------
    cursor.execute("""
    SELECT id, name, email, department, post, resume_path, 
           semantic_score, interview_score,
           psychometric_score, final_score, status
    FROM candidates
    ORDER BY COALESCE(final_score, semantic_score) DESC
    """)
    candidates = cursor.fetchall()

    # --------------------
    # DATE SETUP
    # --------------------
    selected_month = request.args.get("month", type=int) or datetime.now().month
    selected_year = request.args.get("year", type=int) or datetime.now().year
    today_str = datetime.now().strftime("%Y-%m-%d")

    # --------------------
    # ANALYTICS (TODAY ONLY ✅)
    # --------------------
    # Interview Attended
    cursor.execute("""
    SELECT COUNT(*) FROM candidates 
    WHERE interview_score IS NOT NULL
    """)
    attended = cursor.fetchone()[0]

    # Selected
    cursor.execute("""
    SELECT COUNT(*) FROM candidates 
    WHERE final_score >= 50
    """)
    selected = cursor.fetchone()[0]

    # Rejected
    cursor.execute("""
    SELECT COUNT(*) FROM candidates 
    WHERE final_score < 50 AND final_score IS NOT NULL
    """)
    rejected = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM candidates")
    total_candidates = cursor.fetchone()[0]

    # --------------------
    # SAVE / UPDATE ANALYTICS HISTORY ✅
    # --------------------
    cursor.execute("SELECT COUNT(*) FROM analytics_history WHERE date=?", (today_str,))
    exists = cursor.fetchone()[0] > 0

    if exists:
        cursor.execute("""
        UPDATE analytics_history
        SET attended=?, selected=?, rejected=?
        WHERE date=?
        """, (attended, selected, rejected, today_str))
    else:
        cursor.execute("""
        INSERT INTO analytics_history (date, attended, selected, rejected)
        VALUES (?, ?, ?, ?)
        """, (today_str, attended, selected, rejected))

    conn.commit()

    # --------------------
    # LOAD HISTORY FOR CALENDAR
    # --------------------
    cursor.execute("""
    SELECT date, attended, selected, rejected
    FROM analytics_history
    ORDER BY date ASC
    """)
    rows = cursor.fetchall()

    # --------------------
    # MONTHLY CALENDAR
    # --------------------
    month_matrix = calendar.monthcalendar(selected_year, selected_month)
    monthly_calendar = []

    for week in month_matrix:
        week_data = []

        for day in week:
            if day == 0:
                week_data.append(None)
            else:
                day_str = f"{selected_year}-{selected_month:02d}-{day:02d}"
                match = next((r for r in rows if r[0] == day_str), None)

                week_data.append({
                    "day": day,
                    "attended": match[1] if match else 0,
                    "selected": match[2] if match else 0,
                    "rejected": match[3] if match else 0
                })

        monthly_calendar.append(week_data)

    conn.close()

    # --------------------
    # FORMAT CANDIDATES
    # --------------------
    candidate_list = []

    for c in candidates:
        semantic, interview, psychometric, final, status = c[6], c[7], c[8], c[9], c[10]

        candidate_list.append({
            "id": c[0],
            "name": c[1],
            "email": c[2],
            "department": c[3],
            "post": c[4],
            "resume": c[5],
            "semantic": semantic,
            "interview": interview,
            "psychometric": psychometric,
            "final": final,
            "status": status
        })

    selected_day = request.args.get("day", type=int)
    selected_day_data = None

    if selected_day:
        day_str = f"{selected_year}-{selected_month:02d}-{selected_day:02d}"

        match = next((r for r in rows if r[0] == day_str), None)

        selected_day_data = {
            "attended": match[1] if match else 0,
            "selected": match[2] if match else 0,
            "rejected": match[3] if match else 0
        }

    return render_template(
        "admin.html",
        candidates=candidate_list,
        total=total_candidates,
        attended=attended,
        selected=selected,
        rejected=rejected,
        monthly_calendar=monthly_calendar,
        selected_month=selected_month,
        selected_year=selected_year,
        selected_day=selected_day,
        selected_day_data=selected_day_data
    )
# ---------------------------
# ADMIN LOGOUT
# ---------------------------

@app.route("/logout")
def logout():
    session.pop("admin_logged_in", None)
    return redirect("/")

@app.route("/admin/evaluate/<int:candidate_id>")
def admin_evaluate(candidate_id):

    conn = sqlite3.connect("recruitment.db")
    cursor = conn.cursor()

    cursor.execute("""
    SELECT name, email, post, resume_path
    FROM candidates
    WHERE id = ?
    """, (candidate_id,))

    data = cursor.fetchone()

    name = data[0]
    email = data[1]
    post = data[2]
    resume_path = data[3]

    # -------------------------
    # READ RESUME
    # -------------------------
    reader = PdfReader(resume_path)

    resume_text = ""
    for page in reader.pages:
        resume_text += page.extract_text()

    resume_text = resume_text.lower()

    # -------------------------
    # PROMPT
    # -------------------------
    prompt = f"""
    You are an academic recruitment AI system.

    Evaluate the candidate resume.

    Return JSON:

    {{
    "semantic_score": number,
    "research_alignment_score": number,
    "teaching_alignment_score": number,
    "research_summary": "short explanation",
    "teaching_summary": "short explanation",
    "overall_summary": "short evaluation",
    "shortlist": "Yes or No"
    }}

    Resume:
    {resume_text}
    """

    client = get_client()

    # -------------------------
    # TRY GEMINI
    # -------------------------
    try:
        model = client.GenerativeModel("gemini-pro")
        response = model.generate_content(prompt)
        result_text = response.text

        result_text = response.text.strip()

        if result_text.startswith("```"):
            result_text = result_text.replace("```json", "").replace("```", "").strip()

        result = json.loads(result_text)

        # ✅ Scores
        resume_score = normalize(result.get("semantic_score"))
        research = normalize(result.get("research_alignment_score"))
        teaching = normalize(result.get("teaching_alignment_score"))

        # ✅ Fix using summary
        research, teaching = adjust_scores_from_summary(
            research,
            teaching,
            result.get("research_summary", ""),
            result.get("teaching_summary", "")
        )

        # ✅ Final semantic (balanced)
        semantic = round(
            (0.5 * resume_score) +
            (0.3 * teaching) +
            (0.2 * research),
            2
        )

        overall_summary = result["overall_summary"]
        shortlist = result["shortlist"]

    # -------------------------
    # FALLBACK (NO API)
    # -------------------------
    except Exception as e:
        print("API failed → using fallback:", e)

        resume = resume_text.lower()

        # ✅ Rule-based research
        if "publication" in resume or "journal" in resume:
            research = 80
        else:
            research = 10

        # ✅ Rule-based teaching
        if "assistant professor" in resume or "teaching" in resume:
            teaching = 80
        else:
            teaching = 30

        # ✅ Simple semantic
        semantic = round(0.5 * teaching + 0.5 * research, 2)

        overall_summary = "Evaluated using rule-based fallback (API unavailable)"
        shortlist = "Yes" if semantic >= 50 else "No"

    # -------------------------
    # SEND EMAIL
    # -------------------------
    if shortlist == "Yes":

        subject = "Shortlisted for Faculty Recruitment - Meenakshi Sundararajan Engineering College"

        body = f"""
        Dear {name},

        Congratulations! You have been shortlisted for the position of {post}.

        We will contact you for further process.

        Regards,
        Recruitment Team
        """.strip()

        try:
            send_email(email, subject, body)
            print(f"Email sent")
        except Exception as e:
            print("Failed to send email:", e)


    # -------------------------
    # UPDATE DB
    # -------------------------
    cursor.execute("""
    UPDATE candidates
    SET semantic_score=?,
        research_score=?,
        teaching_score=?,
        overall_summary=?,
        shortlist=?,
        updated_at=?,
        status=?
    WHERE id=?
    """, (
        semantic,
        research,
        teaching,
        overall_summary,
        shortlist,
        datetime.now().strftime("%Y-%m-%d"),
        "Pending",
        candidate_id
    ))

    conn.commit()
    conn.close()

    # -------------------------
    # RETURN RESULT PAGE
    # -------------------------
    return render_template(
        "results.html",
        candidate_id=candidate_id,
        semantic_score=semantic,
        research_score=research,
        teaching_score=teaching,
        research_summary=result.get("research_summary", ""),
        teaching_summary=result.get("teaching_summary", ""),
        overall_summary=overall_summary,
        shortlist=shortlist
    )

@app.route("/upload-questions", methods=["GET","POST"])
def upload_questions():

    if request.method == "POST":

        file = request.files["file"]
        filename = file.filename.lower()

        conn = sqlite3.connect("recruitment.db")
        cursor = conn.cursor()

        # -------------------------
        # CSV → PSYCHOMETRIC
        # -------------------------
        if filename.endswith(".csv"):

            df = pd.read_csv(file)

            # optional: remove old psychometric
            cursor.execute("DELETE FROM questions WHERE type='psychometric'")

            for _, row in df.iterrows():
                cursor.execute("""
                INSERT INTO questions
                (department, subject, question, option1, option2, option3, option4, correct_option, type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,(
                    "general",
                    "psychometric",
                    row["question"],
                    row["option1"],
                    row["option2"],
                    row["option3"],
                    row["option4"],
                    row["answer_index"],
                    "psychometric"
                ))

            conn.commit()
            conn.close()

            return "Psychometric uploaded ✅"

        # -------------------------
        # EXCEL → TECHNICAL
        # -------------------------
        elif filename.endswith(".xlsx"):

            xls = pd.ExcelFile(file)

            for sheet in xls.sheet_names:

                department = sheet.lower()
                df = pd.read_excel(xls, sheet_name=sheet)
                df.columns = df.columns.str.strip().str.lower()

                for _, row in df.iterrows():
                    cursor.execute("""
                    INSERT INTO questions
                    (department, subject, question, option1, option2, option3, option4, correct_option, type)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,(
                        department,
                        row["subject"],
                        row["question"],
                        row["option1"],
                        row["option2"],
                        row["option3"],
                        row["option4"],
                        row["correct_option"],
                        "technical"
                    ))

            conn.commit()
            conn.close()

            return "Technical uploaded ✅"

    return render_template("upload_questions.html")

@app.route("/test/<int:candidate_id>")
def start_test(candidate_id):

    if session.get("candidate_id") != candidate_id:
        return redirect("/candidate-login")

    conn = sqlite3.connect("recruitment.db")
    cursor = conn.cursor()

    # get candidate department
    cursor.execute("SELECT department FROM candidates WHERE id=?", (candidate_id,))
    dept = cursor.fetchone()[0]

    # fetch subjects for that department
    cursor.execute("""
    SELECT DISTINCT subject
    FROM questions
    WHERE department=?
    """,(dept.lower(),))

    subjects = cursor.fetchall()

    conn.close()

    return render_template(
        "select_subject.html",
        subjects=subjects,
        candidate_id=candidate_id
    )

@app.route("/generate-test/<int:candidate_id>", methods=["POST"])
def generate_test(candidate_id):

    selected_subjects = request.form.getlist("subjects")

    conn = sqlite3.connect("recruitment.db")
    cursor = conn.cursor()

    questions = []

    for subject in selected_subjects:

        cursor.execute("SELECT department FROM candidates WHERE id=?", (candidate_id,))
        dept = cursor.fetchone()[0]

        cursor.execute("""
        SELECT question, option1, option2, option3, option4, correct_option
        FROM questions
        WHERE subject=? AND department=?
        ORDER BY RANDOM()
        LIMIT 10
        """,(subject, dept.lower()))

        questions += cursor.fetchall()

    conn.close()

    session["test_questions"] = questions

    return render_template(
        "test_page.html",
        questions=questions,
        candidate_id=candidate_id,
        name=session.get("candidate_name", "Candidate")
    )

@app.route("/submit-test/<int:candidate_id>", methods=["POST"])
def submit_test(candidate_id):

    questions = session.get("test_questions")

    if not questions:
        return "Session expired. Restart test."

    score = 0

    for i, q in enumerate(questions):

        selected = request.form.get(f"q{i}")

        if selected and int(selected) == q[5]:
            score += 4   # 25 questions × 4 = 100

    conn = sqlite3.connect("recruitment.db")
    cursor = conn.cursor()

    tech_time = int(request.form.get("tech_time", 0))

    cursor.execute("""
    UPDATE candidates
    SET interview_score=?, tech_time=?, updated_at=?
    WHERE id=?
    """,(score, tech_time, datetime.now().strftime("%Y-%m-%d"), candidate_id))

    conn.commit()
    conn.close()

    session.pop("test_questions", None)

    return render_template(
    "test_result.html",
    candidate_id=candidate_id
)

@app.route("/candidate-login", methods=["GET","POST"])
def candidate_login():

    if request.method == "POST":

        conn = sqlite3.connect("recruitment.db")
        cursor = conn.cursor()

        name = request.form["name"]
        email = request.form["email"]

        cursor.execute("""
        SELECT id, name FROM candidates 
        WHERE email=? AND name=?
        ORDER BY id DESC
        """, (email, name))

        data = cursor.fetchone()

        conn.close()

        if data:
            candidate_id = data[0]
            session["candidate_id"] = candidate_id
            session["candidate_name"] = data[1]

            return redirect(f"/test/{candidate_id}")

        return "Candidate not found"

    return render_template("candidate_login.html")

@app.route("/delete/<int:candidate_id>")
def delete_candidate(candidate_id):

    conn = sqlite3.connect("recruitment.db")
    cursor = conn.cursor()

    cursor.execute("DELETE FROM candidates WHERE id=?", (candidate_id,))
    conn.commit()
    conn.close()

    return redirect("/admin")

@app.route("/test-email")
def test_email():

    try:
        send_email(
            "msdv0722@gmail.com",   # 👉 put your email here
            "Test Email from Render",
            "This is a test email. Deployment working!"
        )
        return "✅ Email sent successfully"
    
    except Exception as e:
        return f"❌ Error: {e}"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

