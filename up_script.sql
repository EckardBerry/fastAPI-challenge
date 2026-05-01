CREATE DATABASE IF NOT EXISTS invoice_management;

CREATE TABLE IF NOT EXISTS invoice_management.customer(
    customer_id INT AUTO_INCREMENT PRIMARY KEY,
    customer_name VARCHAR(50) NOT NULL,
    customer_email VARCHAR(50) NOT NULL
);

INSERT INTO invoice_management.customer (customer_name, customer_email)
VALUES 
('John Doe', 'john.doe@example.com'),
('Jane Smith', 'jane.smith@example.com'),
('Seth Hall', 'seth.hall@paymark.co.nz'),
('Amanda Lee', 'amanda.lee@paymark.co.nz'),
('Robert Smith', 'rob.smith@email.com');

CREATE TABLE IF NOT EXISTS invoice_management.invoice (
    id CHAR(36) PRIMARY KEY NOT NULL,  -- UUID as primary key
    customer_id INT NOT NULL,
    date_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    date_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    job_description VARCHAR(100),
    amount DECIMAL(5,2) NOT NULL,
    invoice_status VARCHAR(10) NOT NULL DEFAULT 'PENDING',
    CONSTRAINT fk_customer_id FOREIGN KEY (customer_id) REFERENCES invoice_management.customer(customer_id)
);


INSERT INTO invoice_management.invoice (id, customer_id, job_description, amount, invoice_status)
VALUES
(UUID(), 1, 'Website Development', 450.75, 'PAID'),
(UUID(), 1, 'Graphic Design Service', 220.50, 'PAID'),
(UUID(), 3, 'SEO Optimization', 175.00, 'PENDING'),
(UUID(), 4, 'Software License Fee', 99.99, 'CANCELLED'),
(UUID(), 3, 'Consultation Service', 300.25, 'PENDING');



