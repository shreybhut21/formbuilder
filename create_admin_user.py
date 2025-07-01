import sqlite3
from datetime import datetime

DB_FILE = "database.db"

def create_admin_user():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Check if admin user already exists
    c.execute("SELECT * FROM user WHERE email=?", ("admin@example.com",))
    if c.fetchone():
        print("Admin user already exists.")
    else:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("INSERT INTO user (uid, name, email, password, is_admin, create_date) VALUES (?, ?, ?, ?, ?, ?)",
                  (1, "Admin", "admin@example.com", "adminpassword", 1, now))
        conn.commit()
        print("Admin user created successfully.")

    # Check if second admin user exists
    c.execute("SELECT * FROM user WHERE email=?", ("admin2@example.com",))
    if c.fetchone():
        print("Second admin user already exists.")
    else:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("INSERT INTO user (uid, name, email, password, is_admin, create_date) VALUES (?, ?, ?, ?, ?, ?)",
                  (2, "Admin2", "admin2@example.com", "adminpassword2", 1, now))
        conn.commit()
        print("Second admin user created successfully.")

    conn.close()

if __name__ == "__main__":
    create_admin_user()
