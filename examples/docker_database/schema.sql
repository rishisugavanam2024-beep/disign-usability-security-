-- Portable synthetic fixture data for the disposable PostgreSQL/MySQL examples.
CREATE TABLE permissions (grant_id VARCHAR(128) PRIMARY KEY);
INSERT INTO permissions (grant_id) VALUES ('g_orders');
CREATE TABLE orders (id INTEGER PRIMARY KEY, product VARCHAR(128));
INSERT INTO orders (id, product) VALUES (1, 'demo-book');
