"""Generate demo-source/seed.sql — a deterministic synthetic e-commerce dataset.

Deliberately 'raw': integer status codes, cents amounts, soft-delete flags,
a few NULL emails — so the dbt staging layer has real cleaning work to do.

Kept in the repo (rather than run once and thrown away) so you can regenerate
with more rows, different products, or a different random seed. Re-running
this script overwrites seed.sql deterministically for the same seed/anchor.

Usage:
  python3 demo-source/generate_seed.py
"""
import random
from datetime import datetime, timedelta

random.seed(42)
NOW = datetime(2026, 7, 1)  # fixed anchor so the file only changes when you edit this script

FIRST = ["Alex", "Sam", "Jordan", "Casey", "Morgan", "Riley", "Taylor", "Quinn",
         "Avery", "Rowan", "Charlie", "Dana", "Eli", "Frankie", "Gabi", "Harper",
         "Iman", "Jules", "Kai", "Lou", "Marion", "Noa", "Ori", "Paz", "Remy", "Sasha"]
LAST = ["Martin", "Bernard", "Dubois", "Moreau", "Laurent", "Garcia", "Silva",
        "Muller", "Rossi", "Novak", "Smith", "Jones", "Brown", "Kim", "Sato",
        "Costa", "Meyer", "Lopez", "Wagner", "Fischer"]
COUNTRIES = ["FR", "DE", "US", "GB", "ES", "IT", "NL", "BE", "CA", "PT"]

PRODUCTS = [
    ("Espresso Machine Pro", "kitchen", 34900), ("French Press Classic", "kitchen", 2900),
    ("Chef Knife 20cm", "kitchen", 8900), ("Cast Iron Skillet", "kitchen", 4500),
    ("Trail Running Shoes", "sports", 12900), ("Yoga Mat Premium", "sports", 3900),
    ("Carbon Road Bike Helmet", "sports", 15900), ("Resistance Bands Set", "sports", 1900),
    ("Noise-Cancelling Headphones", "electronics", 27900), ("Mechanical Keyboard", "electronics", 11900),
    ("4K Webcam", "electronics", 8900), ("Portable SSD 2TB", "electronics", 16900),
    ("Linen Duvet Cover", "home", 9900), ("Ceramic Table Lamp", "home", 6900),
    ("Wool Throw Blanket", "home", 7900), ("Air Purifier Compact", "home", 13900),
    ("Leather Weekender Bag", "travel", 21900), ("Packing Cubes Set", "travel", 2900),
    ("Travel Adapter Universal", "travel", 2400), ("Hardshell Cabin Case", "travel", 17900),
    # Easter egg — not a real SKU, just a nod to whoever ends up reading this catalog closely.
    ("Rubber Duck, Senior Debugging Consultant", "office", 1299),
]

def dt(d): return d.strftime("%Y-%m-%d %H:%M:%S")
def esc(s): return s.replace("'", "''")

lines = [
    "-- Synthetic e-commerce demo data for the medallion starter stack.",
    "-- Generated deterministically by demo-source/generate_seed.py — safe to commit,",
    "-- contains no real data. Loaded automatically by the mysql-demo container on",
    "-- first start (mounted into /docker-entrypoint-initdb.d/).",
    "",
    "CREATE DATABASE IF NOT EXISTS shop;",
    "USE shop;",
    "",
    "CREATE TABLE customers (",
    "  id INT PRIMARY KEY AUTO_INCREMENT,",
    "  full_name VARCHAR(120) NOT NULL,",
    "  email VARCHAR(190),",
    "  country CHAR(2) NOT NULL,",
    "  is_deleted TINYINT(1) NOT NULL DEFAULT 0,  -- soft delete flag, raw style",
    "  date_created DATETIME NOT NULL",
    ");",
    "",
    "CREATE TABLE products (",
    "  id INT PRIMARY KEY AUTO_INCREMENT,",
    "  name VARCHAR(190) NOT NULL,",
    "  category VARCHAR(60) NOT NULL,",
    "  price_cents INT NOT NULL,  -- money stored as integer cents, raw style",
    "  date_created DATETIME NOT NULL",
    ");",
    "",
    "CREATE TABLE orders (",
    "  id INT PRIMARY KEY AUTO_INCREMENT,",
    "  customer_id INT NOT NULL,",
    "  status TINYINT NOT NULL,  -- 0=pending 1=paid 2=shipped 3=cancelled (decoded in staging)",
    "  date_created DATETIME NOT NULL",
    ");",
    "",
    "CREATE TABLE order_items (",
    "  id INT PRIMARY KEY AUTO_INCREMENT,",
    "  order_id INT NOT NULL,",
    "  product_id INT NOT NULL,",
    "  quantity INT NOT NULL,",
    "  unit_price_cents INT NOT NULL  -- price at purchase time (products.price_cents may drift)",
    ");",
    "",
]

# customers — 80, created over the last 2 years, ~8% soft-deleted, a few NULL emails
customers = []
for i in range(1, 81):
    name = f"{random.choice(FIRST)} {random.choice(LAST)}"
    created = NOW - timedelta(days=random.randint(5, 730), hours=random.randint(0, 23))
    email = "NULL" if random.random() < 0.05 else f"'{name.lower().replace(' ', '.')}{i}@example.com'"
    deleted = 1 if random.random() < 0.08 else 0
    customers.append((i, name, email, random.choice(COUNTRIES), deleted, created))
lines.append("INSERT INTO customers (id, full_name, email, country, is_deleted, date_created) VALUES")
lines.append(",\n".join(
    f"({i}, '{esc(n)}', {e}, '{c}', {d}, '{dt(cr)}')" for i, n, e, c, d, cr in customers) + ";")
lines.append("")

# products
lines.append("INSERT INTO products (id, name, category, price_cents, date_created) VALUES")
lines.append(",\n".join(
    f"({i+1}, '{esc(name)}', '{cat}', {price}, '{dt(NOW - timedelta(days=800 - i * 30))}')"
    for i, (name, cat, price) in enumerate(PRODUCTS)) + ";")
lines.append("")

# orders — ~600, weighted to recent months so activity-status marts show all buckets
orders, items = [], []
oid, iid = 0, 0
for cid, _, _, _, deleted, created in customers:
    if deleted:
        continue
    n_orders = random.choices([0, 1, 2, 4, 8, 15], weights=[10, 20, 25, 20, 15, 10])[0]
    for _ in range(n_orders):
        oid += 1
        age = random.choices([20, 75, 200, 500], weights=[35, 25, 25, 15])[0]
        odate = created + (NOW - created) * random.random()
        odate = max(created, NOW - timedelta(days=random.randint(age // 2, age)))
        status = random.choices([0, 1, 2, 3], weights=[5, 25, 60, 10])[0]
        orders.append((oid, cid, status, odate))
        for _ in range(random.randint(1, 4)):
            iid += 1
            pidx = random.randint(0, len(PRODUCTS) - 1)
            base = PRODUCTS[pidx][2]
            paid = int(base * random.choice([1.0, 1.0, 1.0, 0.9, 0.8]))  # occasional discount
            items.append((iid, oid, pidx + 1, random.randint(1, 3), paid))

lines.append("INSERT INTO orders (id, customer_id, status, date_created) VALUES")
lines.append(",\n".join(f"({o}, {c}, {s}, '{dt(d)}')" for o, c, s, d in orders) + ";")
lines.append("")
lines.append("INSERT INTO order_items (id, order_id, product_id, quantity, unit_price_cents) VALUES")
lines.append(",\n".join(f"({i}, {o}, {p}, {q}, {u})" for i, o, p, q, u in items) + ";")
lines.append("")

# read-only user for the extract, mirroring a real prod-replica setup
lines += [
    "-- Read-only user used by the Dagster extract (mirrors a real prod-replica setup).",
    "CREATE USER IF NOT EXISTS 'reader'@'%' IDENTIFIED BY 'readonly';",
    "GRANT SELECT ON shop.* TO 'reader'@'%';",
    "FLUSH PRIVILEGES;",
    "",
]

import os
out = os.path.join(os.path.dirname(__file__), "seed.sql")
with open(out, "w") as f:
    f.write("\n".join(lines))
print(f"wrote {out}: {len(customers)} customers, {len(PRODUCTS)} products, {len(orders)} orders, {len(items)} items")
