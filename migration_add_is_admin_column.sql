-- Migration script to add is_admin column to user table
BEGIN TRANSACTION;

ALTER TABLE user ADD COLUMN is_admin INTEGER DEFAULT 0;

COMMIT;
