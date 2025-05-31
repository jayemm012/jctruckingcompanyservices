from flask import Flask, render_template, request, redirect, session, url_for, flash, send_file
import mysql.connector
import os
import requests
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date, datetime

app = Flask(__name__)
app.secret_key = "your_secret_key"

# Database Configuration
DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "user": os.environ.get("DB_USER", "root"),
    "password": os.environ.get("DB_PASSWORD", "root"),
    "database": os.environ.get("DB_NAME", "jctrucking_company")
}

def get_db_connection():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except mysql.connector.Error as e:
        print(f"Database connection failed: {e}")
        return None

def calculate_age(birthday):
    today = date.today()
    return today.year - birthday.year - ((today.month, today.day) < (birthday.month, birthday.day))

# ROUTES

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/services")
def services():
    return render_template("servicescustomer.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        # Get form data
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip()
        address = request.form.get("address", "").strip()
        contact_no = request.form.get("contact_no", "").strip()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        birthday_str = request.form.get("birthday", "").strip()
        role = request.form.get("role", "").strip()
        print("Role received from form:", repr(role))  # Debug print

        # Basic validation
        if not all([full_name, email, address, contact_no, username, password, birthday_str, role]):
            flash("Please fill in all required fields.", "danger")
            return render_template("register.html")

        if role not in ["users", "driver"]:
            flash("Invalid role selected.", "danger")
            return render_template("register.html")

        # After getting birthday from the form
        try:
            birthday_date = datetime.strptime(birthday_str, "%Y-%m-%d").date()
            age = calculate_age(birthday_date)
        except Exception:
            flash("Invalid birthday format.", "danger")
            return render_template("register.html")

        conn = get_db_connection()
        if conn is None:
            flash("Database connection failed!", "danger")
            return render_template("register.html")
        cursor = conn.cursor()
        try:
            # Check for duplicate username
            if role == "driver":
                cursor.execute("SELECT id FROM driver WHERE username=%s", (username,))
            elif role == "users":
                cursor.execute("SELECT id FROM users WHERE username=%s", (username,))
            if cursor.fetchone():
                flash("Username already exists. Please choose another.", "danger")
                return render_template("register.html")

            # Hash the password
            hashed_password = generate_password_hash(password)

            if role == "driver":
                cursor.execute(
                    "INSERT INTO driver (username, full_name, password, email, contact_no, birthday, address) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (username, full_name, hashed_password, email, contact_no, birthday_str, address)
                )
            elif role == "users":
                cursor.execute(
                    "INSERT INTO users (username, full_name, password, email, contact_no, birthday, address, role) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (username, full_name, hashed_password, email, contact_no, birthday_str, address, role)
                )
            conn.commit()
            flash("Registration successful! Please log in.", "success")
            return redirect(url_for("home"))
        except Exception as e:
            flash(f"Registration failed: {e}", "danger")
            return render_template("register.html")
        finally:
            cursor.close()
            conn.close()
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"].strip()

        if not username or not password:
            flash("Please fill in both fields.", "danger")
            return redirect(url_for("home"))

        conn = get_db_connection()
        if conn is None:
            flash("Database connection failed!", "danger")
            return redirect(url_for("home"))

        cursor = conn.cursor(dictionary=True)
        try:
            # Admin check
            cursor.execute("SELECT * FROM admin WHERE username = %s", (username,))
            admin = cursor.fetchone()
            if admin and admin["password"] == password:
                session["username"] = admin["username"]
                session["is_admin"] = True
                session["role"] = "admin"
                flash("Admin login successful!", "success")
                return redirect(url_for("admindashboard"))

            # Driver check
            cursor.execute("SELECT * FROM driver WHERE username = %s", (username,))
            driver = cursor.fetchone()
            if driver and check_password_hash(driver["password"], password):
                session["username"] = driver["username"]
                session["is_admin"] = False
                session["role"] = "driver"
                flash("Driver login successful!", "success")
                return redirect(url_for("driver_dashboard"))

            # User check
            cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
            user = cursor.fetchone()
            if user and check_password_hash(user["password"], password):
                session["username"] = user["username"]
                session["is_admin"] = False
                session["role"] = user.get("role", "users")
                flash("Login successful!", "success")
                return redirect(url_for("dashboard"))
            else:
                flash("Invalid credentials", "danger")
        except Exception as e:
            flash(f"Error: {e}", "danger")
        finally:
            cursor.close()
            conn.close()
    return render_template("index.html")

# Dashboard page (for regular users)
@app.route("/dashboard")
def dashboard():
    if "username" not in session:
        flash("Please log in first.", "danger")
        return redirect(url_for("home"))
    username = session["username"]
    conn = get_db_connection()
    if conn is None:
        flash("Database connection failed!", "danger")
        return redirect(url_for("home"))
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        cursor.execute("""
            SELECT pickup, dropoff, waste_type, volume, schedule, status
            FROM service_requests
            WHERE username = %s
            ORDER BY id DESC
        """, (username,))
        service_requests = cursor.fetchall()
        # Fetch messages between this user and admin
        cursor.execute("""
            SELECT * FROM user_messages
            WHERE (sender_username = %s AND recipient_username = 'admin')
               OR (sender_username = 'admin' AND recipient_username = %s)
            ORDER BY date ASC
        """, (username, username))
        messages = cursor.fetchall()
        # Fetch payments for this user
        cursor.execute("SELECT * FROM payments WHERE username = %s", (username,))
        payments = cursor.fetchall()
    except Exception as e:
        flash(f"Error: {e}", "danger")
        user = None
        service_requests = []
        messages = []
        payments = []
    finally:
        cursor.close()
        conn.close()
    return render_template(
        "usersdashboard.html",
        user=user,
        service_requests=service_requests,
        messages=messages,
        payments=payments
    )

@app.route('/admindashboard')
def admindashboard():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()
    
    cursor.execute("SELECT * FROM service_requests")
    service_requests = cursor.fetchall()
    
    cursor.execute("SELECT * FROM driver")
    drivers = cursor.fetchall()

    cursor.execute("SELECT * FROM trips")
    trips = cursor.fetchall()

    cursor.execute("SELECT * FROM payments ORDER BY date DESC")
    payments = cursor.fetchall()
    
    cursor.execute("SELECT * FROM announcements ORDER BY date DESC")
    announcements = cursor.fetchall()
    
    cursor.execute("SELECT * FROM user_messages ORDER BY date DESC")
    user_messages = cursor.fetchall()

    # Fetch salary reset info
    cursor.execute("SELECT * FROM driver_salary_reset")
    resets = {row['driver_username']: row['last_reset'] for row in cursor.fetchall()}

    # Calculate salary per driver (₱1500 per trip after last reset)
    driver_salaries = {}
    for driver in drivers:
        last_reset = resets.get(driver['username'])
        if last_reset:
            trip_count = sum(
                1 for trip in trips
                if trip['driver_username'] == driver['username'] and trip['date'] > last_reset
            )
        else:
            trip_count = sum(
                1 for trip in trips
                if trip['driver_username'] == driver['username']
            )
        driver_salaries[driver['username']] = trip_count * 1500

    cursor.close()
    conn.close()

    return render_template(
        "admindashboard.html",
        drivers=drivers,
        driver_salaries=driver_salaries,
        resets=resets,
        users=users,
        service_requests=service_requests,
        trips=trips,
        payments=payments,
        announcements=announcements,
        user_messages=user_messages
    )


@app.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for("home"))


@app.route("/profile", methods=["GET", "POST"])
def profile():
    if "username" not in session:
        flash("Please log in first.", "danger")
        return redirect(url_for("home"))

    username = session["username"]
    conn = get_db_connection()
    if conn is None:
        flash("Database connection failed!", "danger")
        return redirect(url_for("home"))

    cursor = conn.cursor()
    try:
        if request.method == "POST":
            new_username = request.form["username"].strip()
            full_name = request.form["full_name"].strip()
            email = request.form["email"].strip()
            contact_no = request.form["contact_no"].strip()
            age = request.form["age"].strip()
            address = request.form["address"].strip()
            password = request.form["password"].strip()

            if not all([new_username, full_name, email, contact_no, age, address]):
                flash("Please fill in all required fields.", "danger")
                return redirect(url_for("profile"))

            if password:
                cursor.execute("""
                    UPDATE users SET username=%s, full_name=%s, password=%s, email=%s,
                    contact_no=%s, age=%s, address=%s WHERE username=%s
                """, (new_username, full_name, password, email, contact_no, age, address, username))
            else:
                cursor.execute("""
                    UPDATE users SET username=%s, full_name=%s, email=%s,
                    contact_no=%s, age=%s, address=%s WHERE username=%s
                """, (new_username, full_name, email, contact_no, age, address, username))

            conn.commit()
            if new_username != username:
                session["username"] = new_username
            flash("Profile updated successfully!", "success")
            return redirect(url_for("profile"))

        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        if user:
            return render_template("profile.html", user=user)
        flash("User not found.", "danger")
        return redirect(url_for("home"))
    except Exception as e:
        flash(f"Error: {e}", "danger")
        return redirect(url_for("home"))
    finally:
        cursor.close()
        conn.close()

# Submit contact request route (moved out of profile)
@app.route('/submit_contact', methods=['POST'])
def submit_contact_request():
    company = request.form['company']
    address = request.form['address']
    email = request.form['email']
    contact = request.form['contact']
    datetime_val = request.form['datetime']
    client = request.form['client']
    note = request.form['note']
    truck_load = request.form['truck_load']

    conn = get_db_connection()
    if conn is None:
        flash("Database connection failed!", "danger")
        return redirect(url_for("dashboard"))
    cursor = conn.cursor()
    try:
        cursor.execute(
            'INSERT INTO contact_requests (company, address, email, contact, datetime, client, note, truck_load) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
            (company, address, email, contact, datetime_val, client, note, truck_load)
        )
        conn.commit()
        flash('Your request has been submitted!')
    except Exception as e:
        flash(f"Error: {e}", "danger")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('dashboard'))

@app.route("/add-truck", methods=["GET", "POST"])
def add_truck():
    if "username" not in session or not session.get("is_admin"):
        flash("Access denied. Only admins can add trucks.", "danger")
        return redirect(url_for("home"))

    if request.method == "POST":
        truck_number = request.form["truck_number"].strip()
        model = request.form["model"].strip()
        plate_number = request.form["plate_number"].strip()
        capacity = request.form["capacity"].strip()

        if not all([truck_number, model, plate_number, capacity]):
            flash("Please fill in all fields.", "danger")
            return redirect(url_for("add_truck"))

        conn = get_db_connection()
        if conn is None:
            flash("Database connection failed!", "danger")
            return redirect(url_for("add_truck"))

        cursor = conn.cursor()
        try:
            cursor.execute(""" 
                INSERT INTO trucks (truck_number, model, plate_number, capacity)
                VALUES (%s, %s, %s, %s)
            """, (truck_number, model, plate_number, capacity))
            conn.commit()
            flash("Truck added successfully!", "success")
            return redirect(url_for("admindashboard"))
        except Exception as e:
            flash(f"Error: {e}", "danger")
            return redirect(url_for("add_truck"))
        finally:
            cursor.close()
            conn.close()

    return render_template("addtruck.html")

@app.route("/tracker")
def tracker():
    return render_template("customertracker.html")

@app.route("/userManagement")
def userManagement():
    if "username" not in session or not session.get("is_admin"):
        flash("Access denied.", "danger")
        return redirect(url_for("home"))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users")  # or include WHERE/ORDER BY as needed
    users = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("usermanagement.html", users=users)

@app.route("/customer")
def customer():
    if "username" not in session or not session.get("is_admin"):
        flash("Access denied.", "danger")
        return redirect(url_for("home"))
    conn = get_db_connection()
    if conn is None:
        flash("Database connection failed!", "danger")
        return redirect(url_for("admindashboard"))
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM users ORDER BY id DESC")
        users = cursor.fetchall()
    except Exception as e:
        flash(f"Error fetching users: {e}", "danger")
        users = []
    finally:
        cursor.close()
        conn.close()
    return render_template('customer.html', users=users)

@app.route("/Show-Client")
def show_client():
    conn = get_db_connection()
    if conn is None:
        flash("Database connection failed!", "danger")
        return redirect(url_for("admindashboard"))

    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM clients ORDER BY submitted_at DESC")
        clients = cursor.fetchall()
        if clients:
            return render_template("clients.html", clients=clients)
        flash("No clients found.", "warning")
        return redirect(url_for("admindashboard"))
    except Exception as e:
        flash(f"Error fetching clients: {e}", "danger")
        return redirect(url_for("admindashboard"))
    finally:
        cursor.close()
        conn.close()

@app.route("/submit_order", methods=["POST"])
def submit_order():
    service = request.form.get("service")
    service_date = request.form.get("service_date")
    notes = request.form.get("notes")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO service_orders (service, service_date, notes) VALUES (%s, %s, %s)",
        (service, service_date, notes)
    )
    conn.commit()
    cursor.close()
    conn.close()

    return redirect(url_for("services"))

@app.route("/service_request", methods=["POST"])
def service_request():
    if "username" not in session or session.get("is_admin") is None:
        flash("Please log in first.", "danger")
        return redirect(url_for("home"))

    pickup = request.form.get("pickup", "").strip()
    dropoff = request.form.get("dropoff", "").strip()
    waste_type = request.form.get("waste_type", "").strip()
    volume = request.form.get("volume", "").strip()
    schedule = request.form.get("schedule", "").strip()
    username = session["username"]

    if not all([pickup, dropoff, waste_type, volume, schedule]):
        flash("Please fill in all fields.", "danger")
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    if conn is None:
        flash("Database connection failed!", "danger")
        return redirect(url_for("dashboard"))
    
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO service_requests (username, pickup, dropoff, waste_type, volume, schedule, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (username, pickup, dropoff, waste_type, volume, schedule, "Pending"))
        conn.commit()
        flash("Service request submitted successfully!", "success")
        return redirect(url_for("payment_page"))
    except Exception as e:
        flash(f"Error: {e}", "danger")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for("dashboard"))

@app.route('/payment')
def payment_page():
    return render_template('payment.html')

@app.route('/gcash_pay', methods=['POST'])
def gcash_pay():
    # Example: get username from session or form
    username = session.get('username', 'Unknown')
    amount = 5000  # Or get from form/logic
    method = 'GCash'

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO payments (username, amount, method) VALUES (%s, %s, %s)",
        (username, amount, method)
    )
    conn.commit()
    cursor.close()
    conn.close()
    flash("Payment successful!", "success")
    return redirect(url_for('dashboard'))

@app.route('/payment_success')
def payment_success():
    return render_template('payment_success.html')

@app.route('/payment_failure')
def payment_failure():
    return render_template('payment_failure.html')

@app.route('/track_job/<int:job_id>')
def track_job(job_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM service_requests WHERE id = %s', (job_id,))
    job = cursor.fetchone()
    cursor.close()
    conn.close()
    if not job:
        flash('Job not found.', 'error')
        return redirect(url_for('dashboard'))
    return render_template('track_job.html', job=job)

@app.route('/download_invoice/<invoice_id>')
def download_invoice(invoice_id):
    file_path = f'invoices/{invoice_id}.pdf'
    try:
        return send_file(file_path, as_attachment=True)
    except FileNotFoundError:
        flash('Invoice not found.', 'error')
        return redirect(url_for('dashboard'))

@app.route("/transaction_history")
def transaction_history():
    return render_template("transaction_history.html")

@app.route("/staff-driver", methods=["GET", "POST"])
def staff_driver():
    if "username" not in session or not session.get("is_admin"):
        flash("Access denied.", "danger")
        return redirect(url_for("home"))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    if request.method == "POST":
        staff_id = request.form.get("staff_id")
        new_salary = request.form.get("salary")
        cursor.execute("UPDATE staff SET salary=%s WHERE id=%s", (new_salary, staff_id))
        conn.commit()
        flash("Salary updated!", "success")
    cursor.execute("SELECT * FROM staff")
    staff_list = cursor.fetchall()
    cursor.execute("SELECT * FROM users ORDER BY id DESC")
    users = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("admindashboard.html", staff_list=staff_list, users=users, username=session["username"])

@app.route("/admin/services")
def admin_services():
    if "username" not in session or not session.get("is_admin"):
        flash("Access denied.", "danger")
        return redirect(url_for("home"))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM service_requests ORDER BY id DESC")
    service_requests = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("dashboardservice.html", service_requests=service_requests)

@app.route("/update_service_status/<int:service_id>", methods=["POST"])
def update_service_status(service_id):
    if "username" not in session or not session.get("is_admin"):
        flash("Access denied.", "danger")
        return redirect(url_for("admindashboard"))
    new_status = request.form.get("status")
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE service_requests SET status=%s WHERE id=%s", (new_status, service_id))
        conn.commit()
        flash("Status updated!", "success")
    except Exception as e:
        flash(f"Error updating status: {e}", "danger")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for("admindashboard"))

@app.route('/edit_user/<int:user_id>', methods=['POST', 'GET'])
def edit_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        contact_no = request.form.get('contact_no', '').strip()
        address = request.form.get('address', '').strip()
        # Add validation for all required fields
        if not all([full_name, email, contact_no, address]):
            flash("All fields are required.", "danger")
            cursor.close()
            conn.close()
            return redirect(request.url)
        cursor.execute(
            "UPDATE users SET full_name=%s, email=%s, contact_no=%s, address=%s WHERE id=%s",
            (full_name, email, contact_no, address, user_id)
        )
        conn.commit()
        flash("User updated successfully.", "success")
        cursor.close()
        conn.close()
        return redirect(url_for('admindashboard'))
    else:
        cursor.execute("SELECT * FROM users WHERE id=%s", (user_id,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        return render_template('edit_user.html', user=user)

@app.route('/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_deleted=1 WHERE id=%s", (user_id,))
    conn.commit()
    cursor.close()
    conn.close()
    flash("User deleted.", "warning")
    return redirect(url_for('admindashboard'))

@app.route('/recover_user/<int:user_id>', methods=['POST'])
def recover_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_deleted=0 WHERE id=%s", (user_id,))
    conn.commit()
    cursor.close()
    conn.close()
    flash("User recovered.", "success")
    return redirect(url_for('admindashboard'))

@app.route("/driverdashboard")
def driver_dashboard():
    if "username" not in session or session.get("role") != "driver":
        flash("Access denied.", "danger")
        return redirect(url_for("login"))

    driver_username = session["username"]
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch trips for this driver
    cursor.execute(
        "SELECT pickup, dropoff, date FROM trips WHERE driver_username = %s ORDER BY date DESC",
        (driver_username,)
    )
    trips = cursor.fetchall()

    # Fetch last reset date for this driver
    cursor.execute(
        "SELECT last_reset FROM driver_salary_reset WHERE driver_username = %s",
        (driver_username,)
    )
    row = cursor.fetchone()
    last_reset = row['last_reset'] if row else None

    # Calculate salary: only trips after last reset
    if last_reset:
        trip_count = sum(1 for trip in trips if trip['date'] > last_reset)
    else:
        trip_count = len(trips)
    salary = trip_count * 1500

    # Fetch messages between driver and admin
    cursor.execute("""
        SELECT * FROM user_messages
        WHERE (sender_username = %s AND recipient_username = 'admin')
           OR (sender_username = 'admin' AND recipient_username = %s)
        ORDER BY date ASC
    """, (driver_username, driver_username))
    messages = cursor.fetchall()

    cursor.close()
    conn.close()
    return render_template("driverdashboard.html", trips=trips, salary=salary, messages=messages, driver_username=driver_username)

@app.route("/dashboard-driver")
def dashboard_driver():
    if "username" not in session or session.get("role") != "driver":
        flash("Access denied.", "danger")
        return redirect(url_for("home"))
    # Fetch driver-specific data here if needed
    return render_template("driverdashboard.html", username=session["username"])

@app.route("/view_route_driver")
def view_route_driver():
    return "<h2>View Route (Driver)</h2>"

@app.route("/trips_driver")
def trips_driver():
    return "<h2>Trips (Driver)</h2>"

@app.route("/trip_update_driver")
def trip_update_driver():
    return "<h2>Trip Update (Driver)</h2>"
@app.route('/assign_trip', methods=['POST'])
def assign_trip():
    service_id = request.form['service_id']
    driver_username = request.form['driver_username']

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch the service request details
    cursor.execute("SELECT * FROM service_requests WHERE id = %s", (service_id,))
    req = cursor.fetchone()

    if not req:
        flash("Service request not found.", "danger")
        cursor.close()
        conn.close()
        return redirect(url_for('admindashboard'))

    # Insert a new trip for the driver
    cursor.execute(
        "INSERT INTO trips (service_id, driver_username, pickup, dropoff, waste_type, volume, schedule, status) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (
            req['id'],
            driver_username,
            req['pickup'],
            req['dropoff'],
            req['waste_type'],
            req['volume'],
            req['schedule'],
            req['status']
        )
    )

    # Optionally update the service request to show it's assigned
    cursor.execute(
        "UPDATE service_requests SET status = %s, driver_username = %s WHERE id = %s",
        ('Ongoing', driver_username, service_id)
    )

    conn.commit()
    cursor.close()
    conn.close()

    flash("Driver assigned successfully!", "success")
    return redirect(url_for('admindashboard'))

@app.route('/assigntrips')
def assign_trips():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT username FROM driver")
    drivers = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("assigntrips.html", drivers=drivers)

@app.route('/driver_salary')
def driver_salary():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM driver")
    drivers = cursor.fetchall()
    cursor.execute("SELECT * FROM trips")
    trips = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('admindashboard.html', drivers=drivers, trips=trips)

@app.route('/post_announcement', methods=['POST'])
def post_announcement():
    message = request.form['message']
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO announcements (message) VALUES (%s)", (message,))
    conn.commit()
    cursor.close()
    conn.close()
    flash("Announcement posted!", "success")
    return redirect(url_for('admindashboard'))

@app.route('/send_message', methods=['POST'])
def send_message():
    recipient = request.form['recipient']
    message = request.form['message']
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO user_messages (recipient_username, message) VALUES (%s, %s)",
        (recipient, message)
    )
    conn.commit()
    cursor.close()
    conn.close()
    flash(f"Message sent to {recipient}!", "success")
    return redirect(url_for('admindashboard'))

# Admin sends message to user
@app.route('/admin_send_message', methods=['POST'])
def admin_send_message():
    sender = 'admin'
    recipient = request.form['recipient']
    message = request.form['message']
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO user_messages (sender_username, recipient_username, message) VALUES (%s, %s, %s)",
        (sender, recipient, message)
    )
    conn.commit()
    cursor.close()
    conn.close()
    flash(f"Message sent to {recipient}!", "success")
    return redirect(url_for('admindashboard'))

@app.route('/usersdashboard', methods=['GET', 'POST'])
def usersdashboard():
    username = session['username']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch user info
    cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
    user = cursor.fetchone()

    # Fetch messages between this user and admin
    cursor.execute("""
        SELECT * FROM user_messages
        WHERE (sender_username = %s AND recipient_username = 'admin')
           OR (sender_username = 'admin' AND recipient_username = %s)
        ORDER BY date ASC
    """, (username, username))
    messages = cursor.fetchall()

    # Fetch service requests for this user
    cursor.execute("SELECT * FROM service_requests WHERE username = %s", (username,))
    service_requests = cursor.fetchall()

    # Fetch payments for this user
    cursor.execute("SELECT * FROM payments WHERE username = %s", (username,))
    payments = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "usersdashboard.html",
        user=user,
        messages=messages,
        service_requests=service_requests,
        payments=payments
    )


@app.route('/user_send_message', methods=['POST'])
def user_send_message():
    sender = session['username']
    recipient = request.form['recipient']  # should be 'admin'
    message = request.form['message']
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO user_messages (sender_username, recipient_username, message) VALUES (%s, %s, %s)",
        (sender, recipient, message)
    )
    conn.commit()
    cursor.close()
    conn.close()
    flash("Message sent!", "success")
    return redirect(url_for('usersdashboard'))

@app.route('/reset_driver_salary/<username>', methods=['POST'])
def reset_driver_salary(username):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "REPLACE INTO driver_salary_reset (driver_username, last_reset) VALUES (%s, NOW())",
        (username,)
    )
    conn.commit()
    cursor.close()
    conn.close()
    flash(f"Salary for {username} has been reset.", "success")
    return redirect(url_for('admindashboard'))

@app.route('/driver_send_message', methods=['POST'])
def driver_send_message():
    if "username" not in session or session.get("role") != "driver":
        flash("Access denied.", "danger")
        return redirect(url_for("login"))
    sender = session['username']
    recipient = request.form['recipient']  # should be 'admin'
    message = request.form['message']
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO user_messages (sender_username, recipient_username, message) VALUES (%s, %s, %s)",
        (sender, recipient, message)
    )
    conn.commit()
    cursor.close()
    conn.close()
    flash("Message sent!", "success")
    # Redirect with section parameter
    return redirect(url_for('driver_dashboard', section='driver-messages-section'))

if __name__ == "__main__":
    app.run(debug=True)



