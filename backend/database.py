"""SQLite setup and database helpers for Shopsika."""
from __future__ import annotations

import os
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("DATABASE_PATH", str(BASE_DIR / "shopsika.db"))).resolve()


def get_connection() -> sqlite3.Connection:
    """Return a connection configured for safe row access and foreign keys."""
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def db_connection() -> Iterator[sqlite3.Connection]:
    connection = get_connection()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db() -> None:
    """Create tables and seed a small demo catalog on first startup."""
    with db_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                category TEXT NOT NULL,
                price REAL NOT NULL CHECK(price >= 0),
                price_paise INTEGER GENERATED ALWAYS AS (CAST(ROUND(price * 100) AS INTEGER)) VIRTUAL,
                brand TEXT NOT NULL DEFAULT '',
                specifications TEXT NOT NULL DEFAULT '',
                stock INTEGER NOT NULL DEFAULT 0 CHECK(stock >= 0),
                image_url TEXT NOT NULL DEFAULT '',
                rating REAL NOT NULL DEFAULT 4.0 CHECK(rating >= 0 AND rating <= 5),
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_number TEXT NOT NULL UNIQUE,
                customer_name TEXT NOT NULL,
                email TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL,
                delivery_address TEXT NOT NULL,
                total REAL NOT NULL CHECK(total >= 0),
                payment_method TEXT NOT NULL DEFAULT 'demo',
                payment_status TEXT NOT NULL DEFAULT 'demo_not_charged',
                order_status TEXT NOT NULL DEFAULT 'confirmed',
                customer_key TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                product_id INTEGER REFERENCES products(id) ON DELETE SET NULL,
                product_name TEXT NOT NULL,
                unit_price REAL NOT NULL,
                quantity INTEGER NOT NULL CHECK(quantity > 0),
                line_total REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS shopping_sessions (
                session_id TEXT PRIMARY KEY,
                search_product_ids TEXT NOT NULL DEFAULT '[]',
                selected_product_id INTEGER REFERENCES products(id),
                stage TEXT NOT NULL DEFAULT 'shopping',
                quantity_confirmed INTEGER NOT NULL DEFAULT 0,
                customer_name TEXT NOT NULL DEFAULT '',
                email TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '',
                delivery_address TEXT NOT NULL DEFAULT '',
                payment_method TEXT NOT NULL DEFAULT '',
                order_number TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                customer_key TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS auth_sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS shopping_session_items (
                session_id TEXT NOT NULL REFERENCES shopping_sessions(session_id) ON DELETE CASCADE,
                product_id INTEGER NOT NULL REFERENCES products(id),
                quantity INTEGER NOT NULL CHECK(quantity > 0 AND quantity <= 10),
                PRIMARY KEY(session_id, product_id)
            );
            CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at);
            CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id ON auth_sessions(user_id);
            """
        )

        # Product prices are stored in rupees for direct inspection. A generated
        # paise value preserves the integer arithmetic used by orders and APIs.
        product_columns = {row["name"] for row in conn.execute("PRAGMA table_xinfo(products)")}
        if "price" not in product_columns and "price_paise" in product_columns:
            conn.execute("ALTER TABLE products RENAME COLUMN price_paise TO price")
            conn.execute("UPDATE products SET price = ROUND(price / 100.0, 2)")
            product_columns = {row["name"] for row in conn.execute("PRAGMA table_xinfo(products)")}
        if "price_paise" not in product_columns:
            conn.execute(
                "ALTER TABLE products ADD COLUMN price_paise INTEGER GENERATED ALWAYS AS (CAST(ROUND(price * 100) AS INTEGER)) VIRTUAL"
            )
            product_columns.add("price_paise")
        if "rating" not in product_columns:
            conn.execute("ALTER TABLE products ADD COLUMN rating REAL NOT NULL DEFAULT 4.0 CHECK(rating >= 0 AND rating <= 5)")

        order_columns = {row["name"] for row in conn.execute("PRAGMA table_info(orders)")}
        if "customer_key" not in order_columns:
            conn.execute("ALTER TABLE orders ADD COLUMN customer_key TEXT NOT NULL DEFAULT ''")

        # Store order prices in rupees, like products.price. Convert existing
        # paise values while rebuilding both tables with REAL price columns.
        order_columns = {row["name"] for row in conn.execute("PRAGMA table_info(orders)")}
        item_columns = {row["name"] for row in conn.execute("PRAGMA table_info(order_items)")}
        if "total_paise" in order_columns or "unit_price_paise" in item_columns:
            conn.execute("""CREATE TABLE orders_v2 (
                id INTEGER PRIMARY KEY AUTOINCREMENT, order_number TEXT NOT NULL UNIQUE,
                customer_name TEXT NOT NULL, email TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL,
                delivery_address TEXT NOT NULL, total REAL NOT NULL CHECK(total >= 0),
                payment_method TEXT NOT NULL DEFAULT 'demo', payment_status TEXT NOT NULL DEFAULT 'demo_not_charged',
                order_status TEXT NOT NULL DEFAULT 'confirmed', customer_key TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""")
            old_total = "total_paise / 100.0" if "total_paise" in order_columns else "total"
            conn.execute(f"""INSERT INTO orders_v2
                (id,order_number,customer_name,email,phone,delivery_address,total,payment_method,payment_status,order_status,customer_key,created_at)
                SELECT id,order_number,customer_name,email,phone,delivery_address,{old_total},payment_method,payment_status,order_status,customer_key,created_at FROM orders""")
            conn.execute("""CREATE TABLE order_items_v2 (
                id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL REFERENCES orders_v2(id) ON DELETE CASCADE,
                product_id INTEGER REFERENCES products(id) ON DELETE SET NULL, product_name TEXT NOT NULL,
                unit_price REAL NOT NULL, quantity INTEGER NOT NULL CHECK(quantity > 0), line_total REAL NOT NULL
            )""")
            old_unit = "unit_price_paise / 100.0" if "unit_price_paise" in item_columns else "unit_price"
            old_line = "line_total_paise / 100.0" if "line_total_paise" in item_columns else "line_total"
            conn.execute(f"""INSERT INTO order_items_v2
                (id,order_id,product_id,product_name,unit_price,quantity,line_total)
                SELECT id,order_id,product_id,product_name,{old_unit},quantity,{old_line} FROM order_items""")
            conn.execute("DROP TABLE order_items")
            conn.execute("DROP TABLE orders")
            conn.execute("ALTER TABLE orders_v2 RENAME TO orders")
            conn.execute("ALTER TABLE order_items_v2 RENAME TO order_items")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_customer_key ON orders(customer_key, created_at DESC)")

        # Add session fields to databases created by earlier versions without touching orders/products.
        session_columns = {row["name"] for row in conn.execute("PRAGMA table_info(shopping_sessions)")}
        if "search_product_ids" not in session_columns:
            conn.execute("ALTER TABLE shopping_sessions ADD COLUMN search_product_ids TEXT NOT NULL DEFAULT '[]'")
        if "selected_product_id" not in session_columns:
            conn.execute("ALTER TABLE shopping_sessions ADD COLUMN selected_product_id INTEGER REFERENCES products(id)")
        if "quantity_confirmed" not in session_columns:
            conn.execute("ALTER TABLE shopping_sessions ADD COLUMN quantity_confirmed INTEGER NOT NULL DEFAULT 0")

        # Retire everything before syncing the curated demo catalog.
        conn.execute("UPDATE products SET is_active = 0")
        seed_file = BASE_DIR / "demo_products.json"
        if seed_file.exists():
            demo_products = json.loads(seed_file.read_text(encoding="utf-8"))
            for product in demo_products:
                values = (
                    product["name"], product["description"], product["category"],
                    round(float(product["price"]), 2), product.get("brand", ""),
                    product.get("specifications", ""), max(0, int(product.get("stock", 0))),
                    product.get("image_url", ""),
                    float(product.get("rating", 4.0)),
                )
                existing = conn.execute(
                    "SELECT id FROM products WHERE name = ? COLLATE NOCASE",
                    (product["name"],),
                ).fetchone()
                if existing is None:
                    conn.execute(
                        """INSERT INTO products
                        (name, description, category, price, brand, specifications, stock, image_url, rating)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        values,
                    )
                else:
                    conn.execute(
                        """UPDATE products SET description = ?, category = ?, price = ?,
                           brand = ?, specifications = ?, image_url = ?, rating = ?, is_active = 1 WHERE id = ?""",
                        (product["description"], product["category"], round(float(product["price"]), 2),
                         product.get("brand", ""), product.get("specifications", ""), values[-2], values[-1], existing["id"]),
                    )

            # Keep order line snapshots while removing obsolete product records.
            # Their saved names and prices remain in order_items; the optional
            # product_id is cleared when its catalog product is retired.
            conn.execute("""UPDATE order_items SET product_id = NULL
                WHERE product_id IN (SELECT id FROM products WHERE is_active = 0)""")
            conn.execute("""DELETE FROM shopping_session_items
                WHERE product_id IN (SELECT id FROM products WHERE is_active = 0)""")
            conn.execute("""UPDATE shopping_sessions SET selected_product_id = NULL
                WHERE selected_product_id IN (SELECT id FROM products WHERE is_active = 0)""")
            inactive_ids = {row["id"] for row in conn.execute("SELECT id FROM products WHERE is_active = 0")}
            for row in conn.execute("SELECT session_id, search_product_ids FROM shopping_sessions").fetchall():
                try:
                    ids = json.loads(row["search_product_ids"] or "[]")
                except (TypeError, ValueError):
                    ids = []
                filtered_ids = [item_id for item_id in ids if item_id not in inactive_ids]
                if filtered_ids != ids:
                    conn.execute("UPDATE shopping_sessions SET search_product_ids = ? WHERE session_id = ?",
                                 (json.dumps(filtered_ids), row["session_id"]))
            conn.execute(
                "DELETE FROM products WHERE is_active = 0"
            )
