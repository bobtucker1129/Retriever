-- Retriever Inventory - Schema (MySQL)
--
-- Customer fulfillment inventory tracking for Boone Graphics.
-- Stores operational/workflow data owned by Retriever (not MIS business data).
--
-- Run this on the MySQL server (192.168.33.243).

CREATE DATABASE IF NOT EXISTS retriever_inventory
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE retriever_inventory;

-- ---------------------------------------------------------------------------
-- Sites (physical locations)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sites (
  id INT NOT NULL AUTO_INCREMENT,
  name VARCHAR(100) NOT NULL,
  address TEXT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (id),
  UNIQUE KEY uq_sites_name (name)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------------
-- Zones (areas within a site)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS zones (
  id INT NOT NULL AUTO_INCREMENT,
  site_id INT NOT NULL,
  name VARCHAR(100) NOT NULL,
  description TEXT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (id),
  UNIQUE KEY uq_zones_site_name (site_id, name),
  CONSTRAINT fk_zones_site FOREIGN KEY (site_id) REFERENCES sites (id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------------
-- Customers (with optional parent/child for sub-programs)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS customers (
  id INT NOT NULL AUTO_INCREMENT,
  parent_id INT NULL,
  name VARCHAR(200) NOT NULL,
  primary_contact_username VARCHAR(50) NULL,
  mis_account_id INT NULL,
  contact_name VARCHAR(200) NULL,
  contact_email VARCHAR(200) NULL,
  count_frequency ENUM('monthly', 'quarterly', 'semi_annual', 'annual', 'as_needed')
    NOT NULL DEFAULT 'as_needed',
  last_count_date DATE NULL,
  notes TEXT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (id),
  CONSTRAINT fk_customers_parent FOREIGN KEY (parent_id) REFERENCES customers (id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------------
-- Products
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS products (
  id INT NOT NULL AUTO_INCREMENT,
  customer_id INT NOT NULL,
  zone_id INT NOT NULL,
  sku VARCHAR(50) NOT NULL,
  name VARCHAR(300) NOT NULL,
  description TEXT NULL,
  unit_type ENUM('individual', 'pack') NOT NULL DEFAULT 'individual',
  pack_size INT NULL,
  quantity INT NOT NULL DEFAULT 0,
  low_threshold INT NULL,
  cost_per_unit DECIMAL(10,2) NULL,
  notification_emails TEXT NULL,
  status ENUM('active', 'retired') NOT NULL DEFAULT 'active',
  replaced_by_id INT NULL,
  created_by VARCHAR(50) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (id),
  UNIQUE KEY uq_products_sku (sku),
  KEY idx_products_customer_status (customer_id, status),
  KEY idx_products_zone (zone_id),
  CONSTRAINT fk_products_customer FOREIGN KEY (customer_id) REFERENCES customers (id),
  CONSTRAINT fk_products_zone FOREIGN KEY (zone_id) REFERENCES zones (id),
  CONSTRAINT fk_products_replaced_by FOREIGN KEY (replaced_by_id) REFERENCES products (id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------------
-- Transactions (stock movements)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS transactions (
  id INT NOT NULL AUTO_INCREMENT,
  product_id INT NOT NULL,
  action ENUM('pull', 'add', 'count_adjustment') NOT NULL,
  quantity INT NOT NULL,
  quantity_before INT NOT NULL,
  quantity_after INT NOT NULL,
  order_reference VARCHAR(200) NULL,
  override_reason TEXT NULL,
  performed_by VARCHAR(50) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

  PRIMARY KEY (id),
  KEY idx_transactions_product_date (product_id, created_at),
  KEY idx_transactions_user_date (performed_by, created_at),
  CONSTRAINT fk_transactions_product FOREIGN KEY (product_id) REFERENCES products (id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------------
-- Inventory Counts (physical count sessions)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS inventory_counts (
  id INT NOT NULL AUTO_INCREMENT,
  initiated_by VARCHAR(50) NOT NULL,
  status ENUM('in_progress', 'review', 'completed', 'canceled') NOT NULL DEFAULT 'in_progress',
  scope_description TEXT NULL,
  discrepancy_threshold_pct INT NOT NULL DEFAULT 20,
  started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at DATETIME NULL,
  completed_by VARCHAR(50) NULL,

  PRIMARY KEY (id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------------
-- Count Items (per-product snapshots within a count)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS count_items (
  id INT NOT NULL AUTO_INCREMENT,
  count_id INT NOT NULL,
  product_id INT NOT NULL,
  recorded_quantity INT NOT NULL,
  counted_quantity INT NULL,
  discrepancy INT NULL,
  flagged BOOLEAN NOT NULL DEFAULT FALSE,
  approved BOOLEAN NULL,
  approved_by VARCHAR(50) NULL,
  counted_by VARCHAR(50) NULL,
  counted_at DATETIME NULL,

  PRIMARY KEY (id),
  KEY idx_count_items_count (count_id),
  KEY idx_count_items_product (product_id),
  CONSTRAINT fk_count_items_count FOREIGN KEY (count_id) REFERENCES inventory_counts (id),
  CONSTRAINT fk_count_items_product FOREIGN KEY (product_id) REFERENCES products (id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------------
-- Count Scope (which sites/zones/customers a count covers)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS count_scope (
  count_id INT NOT NULL,
  scope_type ENUM('site', 'zone', 'customer') NOT NULL,
  scope_id INT NOT NULL,

  PRIMARY KEY (count_id, scope_type, scope_id),
  CONSTRAINT fk_count_scope_count FOREIGN KEY (count_id) REFERENCES inventory_counts (id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------------
-- Audit Log (lifecycle events for all entities)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_log (
  id INT NOT NULL AUTO_INCREMENT,
  entity_type ENUM('product', 'customer', 'zone', 'site', 'count') NOT NULL,
  entity_id INT NOT NULL,
  action VARCHAR(50) NOT NULL,
  changes JSON NULL,
  performed_by VARCHAR(50) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

  PRIMARY KEY (id),
  KEY idx_audit_entity (entity_type, entity_id),
  KEY idx_audit_user_date (performed_by, created_at)
) ENGINE=InnoDB;
