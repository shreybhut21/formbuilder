-- Migration script to add logo_data column to submissions table
ALTER TABLE submissions ADD COLUMN logo_data TEXT;
