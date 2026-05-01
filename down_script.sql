-- Remove all data from tables
DELETE FROM invoice_management.invoice;
DELETE FROM invoice_management.customer;

-- Drop foreign key constraint before dropping tables
ALTER TABLE invoice_management.invoice DROP FOREIGN KEY fk_customer_id;

-- Drop tables (invoice first to avoid foreign key issues)
DROP TABLE IF EXISTS invoice_management.invoice;
DROP TABLE IF EXISTS invoice_management.customer;

-- Drop database (optional, only if you want to completely remove it)
DROP DATABASE IF EXISTS invoice_management;