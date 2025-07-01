-- Manual migration script to remove "country" column from user table in SQLite

BEGIN TRANSACTION;

PRAGMA foreign_keys=off;

-- Create new user table without "country" column
CREATE TABLE user_new (
    uid INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    phone TEXT,
    create_date TEXT DEFAULT CURRENT_TIMESTAMP,
    write_date TEXT
);

-- Copy data from old user table to new user table excluding "country"
INSERT INTO user_new (uid, name, email, password, phone, create_date, write_date)
SELECT uid, name, email, password, phone, create_date, write_date FROM user;

-- Drop old user table
DROP TABLE user;

-- Rename new user table to user
ALTER TABLE user_new RENAME TO user;

PRAGMA foreign_keys=on;

COMMIT;
