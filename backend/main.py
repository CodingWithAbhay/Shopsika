"""Shopsika API: FastAPI + Groq + SQLite. Run with: uvicorn main:app --reload"""
from __future__ import annotations

import os
import hashlib
import hmac
import secrets
import sqlite3
import re
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from agent import chat_with_agent
from database import db_connection, init_db
from schemas import AccountSignIn, AccountSignUp, ChatRequest, ChatResponse, OrderCreate, OrderItemOut, OrderOut, ProductOut


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Shopsika API",
    description="AI shopping agent API. Demo checkout creates a simulated order and never charges a card.",
    version="1.0.0",
    lifespan=lifespan,
)

allowed_origins = [origin.strip() for origin in os.getenv("FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


def product_dict(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"], "name": row["name"], "description": row["description"],
        "category": row["category"], "price": round(row["price_paise"] / 100, 2),
        "brand": row["brand"], "specifications": row["specifications"],
        "stock": row["stock"], "image_url": row["image_url"], "rating": row["rating"], "in_stock": row["stock"] > 0,
    }


def _customer_key(request: Request, response: Response) -> str:
    user = _authenticated_user(request)
    if user:
        return user["customer_key"]
    key = request.cookies.get("shopsika_customer_key", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,100}", key):
        key = secrets.token_urlsafe(36)
        response.set_cookie(
            "shopsika_customer_key", key, max_age=60 * 60 * 24 * 365,
            httponly=True, secure=request.url.scheme == "https", samesite="lax", path="/api",
        )
    return key


def _authenticated_user(request: Request) -> Any | None:
    token = request.cookies.get("shopsika_session", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,100}", token):
        return None
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with db_connection() as conn:
        return conn.execute(
            """SELECT users.id,users.name,users.email,users.customer_key
               FROM auth_sessions JOIN users ON users.id=auth_sessions.user_id
               WHERE auth_sessions.token_hash=? AND auth_sessions.expires_at>datetime('now')""",
            (token_hash,),
        ).fetchone()


def _issue_auth_session(conn: Any, user_id: int, response: Response, request: Request) -> None:
    token = secrets.token_urlsafe(36)
    conn.execute("DELETE FROM auth_sessions WHERE expires_at<=datetime('now')")
    conn.execute("INSERT INTO auth_sessions(token_hash,user_id,expires_at) VALUES(?,?,datetime('now','+30 days'))",
                 (hashlib.sha256(token.encode("utf-8")).hexdigest(), user_id))
    response.set_cookie("shopsika_session", token, max_age=60 * 60 * 24 * 30,
                        httponly=True, secure=request.url.scheme == "https", samesite="lax", path="/api")


def _password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=64)
    return f"scrypt${salt.hex()}${digest.hex()}"


def _password_matches(password: str, stored: str) -> bool:
    try:
        algorithm, salt_hex, digest_hex = stored.split("$", 2)
        if algorithm != "scrypt":
            return False
        actual = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1, dklen=64)
        return hmac.compare_digest(actual.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def _valid_email(email: str) -> bool:
    return bool(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email.strip()))


def _move_guest_orders(conn: Any, request: Request, customer_key: str) -> None:
    guest_key = request.cookies.get("shopsika_customer_key", "")
    if guest_key and guest_key != customer_key and re.fullmatch(r"[A-Za-z0-9_-]{32,100}", guest_key):
        conn.execute("UPDATE orders SET customer_key=? WHERE customer_key=?", (customer_key, guest_key))


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "shopsika-api"}


@app.get("/api/auth/me")
def auth_me(request: Request) -> dict[str, Any]:
    user = _authenticated_user(request)
    if not user:
        return {"authenticated": False}
    return {"authenticated": True, "name": user["name"], "email": user["email"]}


@app.post("/api/auth/signup")
def sign_up(payload: AccountSignUp, request: Request, response: Response) -> dict[str, Any]:
    email = payload.email.strip().lower()
    name = payload.name.strip()
    if not _valid_email(email):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    if len(name) < 2:
        raise HTTPException(status_code=422, detail="Name must contain at least 2 characters.")
    customer_key = secrets.token_urlsafe(36)
    try:
        with db_connection() as conn:
            cursor = conn.execute("INSERT INTO users(name,email,password_hash,customer_key) VALUES(?,?,?,?)",
                                  (name, email, _password_hash(payload.password), customer_key))
            _move_guest_orders(conn, request, customer_key)
            _issue_auth_session(conn, cursor.lastrowid, response, request)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="An account with that email already exists. Sign in instead.") from exc
    return {"authenticated": True, "name": name, "email": email}


@app.post("/api/auth/signin")
def sign_in(payload: AccountSignIn, request: Request, response: Response) -> dict[str, Any]:
    email = payload.email.strip().lower()
    if not _valid_email(email):
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    with db_connection() as conn:
        user = conn.execute("SELECT id,name,email,password_hash,customer_key FROM users WHERE email=? COLLATE NOCASE", (email,)).fetchone()
    if not user or not _password_matches(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    with db_connection() as conn:
        _move_guest_orders(conn, request, user["customer_key"])
        _issue_auth_session(conn, user["id"], response, request)
    return {"authenticated": True, "name": user["name"], "email": user["email"]}


@app.post("/api/auth/signout")
def sign_out(request: Request, response: Response) -> dict[str, bool]:
    token = request.cookies.get("shopsika_session", "")
    if token:
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with db_connection() as conn:
            conn.execute("DELETE FROM auth_sessions WHERE token_hash=?", (token_hash,))
    response.delete_cookie("shopsika_session", path="/api", httponly=True,
                           secure=request.url.scheme == "https", samesite="lax")
    return {"authenticated": False}


@app.get("/api/products", response_model=list[ProductOut])
def list_products(
    q: str = Query(default="", max_length=200, description="Search name, description, brand, category, or specs"),
    category: str | None = Query(default=None, max_length=80),
    max_price: float | None = Query(default=None, ge=0, le=10000000),
    in_stock: bool | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=500),
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM products WHERE is_active = 1"
    params: list[Any] = []
    if q.strip():
        sql += " AND (name LIKE ? OR description LIKE ? OR brand LIKE ? OR category LIKE ? OR specifications LIKE ?)"
        wildcard = f"%{q.strip()}%"
        params.extend([wildcard] * 5)
    if category and category.strip():
        sql += " AND LOWER(category) = LOWER(?)"
        params.append(category.strip())
    if max_price is not None:
        sql += " AND price_paise <= ?"
        params.append(int(max_price * 100))
    if in_stock is True:
        sql += " AND stock > 0"
    elif in_stock is False:
        sql += " AND stock = 0"
    sql += " ORDER BY (stock > 0) DESC, price_paise ASC LIMIT ?"
    params.append(limit)
    with db_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [product_dict(row) for row in rows]


@app.get("/api/products/{product_id}", response_model=ProductOut)
def get_product(product_id: int) -> dict[str, Any]:
    with db_connection() as conn:
        row = conn.execute("SELECT * FROM products WHERE id = ? AND is_active = 1", (product_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product_dict(row)


@app.post("/api/chat", response_model=ChatResponse)
def chat(chat_request: ChatRequest, request: Request, response: Response) -> dict[str, Any]:
    try:
        customer_key = _customer_key(request, response)
        return chat_with_agent(chat_request.message.strip(), chat_request.history, chat_request.session_id, customer_key)
    except RuntimeError as exc:
        # Configuration problems are actionable and are not silently disguised as AI responses.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        # Keep internal provider details out of the response to the browser.
        print(f"Groq chat error: {type(exc).__name__}: {exc}")
        raise HTTPException(status_code=502, detail="The AI shopping assistant is temporarily unavailable. Check the backend terminal and try again.") from exc


@app.post("/api/orders", response_model=OrderOut, status_code=201)
def create_demo_order(request: OrderCreate, http_request: Request, response: Response) -> dict[str, Any]:
    """Create a simulated order only after explicit confirmation; no payment is processed."""
    if not request.confirm_demo_order:
        raise HTTPException(status_code=400, detail="Please confirm the demo order before checkout.")

    # Combine duplicate product IDs so inventory is checked and decremented correctly.
    quantities: dict[int, int] = {}
    for item in request.items:
        quantities[item.product_id] = quantities.get(item.product_id, 0) + item.quantity
    if any(quantity > 10 for quantity in quantities.values()):
        raise HTTPException(status_code=422, detail="Maximum quantity per product is 10.")

    order_number = "SHOP-DEMO-" + secrets.token_hex(4).upper()
    customer_key = _customer_key(http_request, response)
    order_items: list[dict[str, Any]] = []
    total = 0.0

    try:
        with db_connection() as conn:
            # BEGIN IMMEDIATE reserves the write transaction while stock is checked and updated.
            conn.execute("BEGIN IMMEDIATE")
            for product_id, quantity in quantities.items():
                row = conn.execute(
                    "SELECT id, name, price, stock, is_active FROM products WHERE id = ?",
                    (product_id,),
                ).fetchone()
                if row is None or not row["is_active"]:
                    raise HTTPException(status_code=404, detail=f"Product {product_id} was not found.")
                if row["stock"] < quantity:
                    raise HTTPException(status_code=409, detail=f"Not enough stock for {row['name']}. Available: {row['stock']}.")
                line_total = round(row["price"] * quantity, 2)
                total = round(total + line_total, 2)
                order_items.append({
                    "product_id": row["id"], "product_name": row["name"],
                    "unit_price": row["price"], "quantity": quantity,
                    "line_total": line_total,
                })

            cursor = conn.execute(
                """INSERT INTO orders
                (order_number, customer_name, email, phone, delivery_address, total,
                 payment_method, payment_status, order_status, customer_key)
                VALUES (?, ?, ?, ?, ?, ?, 'demo', 'demo_not_charged', 'confirmed', ?)""",
                (order_number, request.customer_name.strip(), request.email.strip(), request.phone.strip(),
                 request.delivery_address.strip(), total, customer_key),
            )
            order_id = cursor.lastrowid
            for item in order_items:
                conn.execute(
                    """INSERT INTO order_items
                    (order_id, product_id, product_name, unit_price, quantity, line_total)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    (order_id, item["product_id"], item["product_name"], item["unit_price"],
                     item["quantity"], item["line_total"]),
                )
                conn.execute("UPDATE products SET stock = stock - ? WHERE id = ?", (item["quantity"], item["product_id"]))
    except sqlite3.Error as exc:
        print(f"SQLite order error: {type(exc).__name__}: {exc}")
        raise HTTPException(status_code=500, detail="Could not save the demo order. Please try again.") from exc

    return {
        "order_number": order_number,
        "customer_name": request.customer_name.strip(),
        "total": round(total, 2),
        "currency": "INR",
        "payment_method": "demo",
        "payment_status": "demo_not_charged",
        "order_status": "confirmed",
        "message": "Demo order placed successfully. No real payment was taken.",
        "items": [
            {
                "product_id": item["product_id"], "product_name": item["product_name"],
                "unit_price": round(item["unit_price"], 2),
                "quantity": item["quantity"], "line_total": round(item["line_total"], 2),
            }
            for item in order_items
        ],
    }


@app.get("/api/orders")
def list_customer_orders(request: Request, response: Response) -> list[dict[str, Any]]:
    """List orders associated with this browser's private customer cookie."""
    customer_key = _customer_key(request, response)
    with db_connection() as conn:
        rows = conn.execute("SELECT * FROM orders WHERE customer_key=? ORDER BY created_at DESC,id DESC", (customer_key,)).fetchall()
        output = []
        for order in rows:
            items = conn.execute(
                "SELECT product_id,product_name,unit_price,quantity,line_total FROM order_items WHERE order_id=? ORDER BY id",
                (order["id"],),
            ).fetchall()
            output.append({
                "order_number": order["order_number"], "customer_name": order["customer_name"],
                "email": order["email"], "phone": order["phone"], "delivery_address": order["delivery_address"],
                "total": round(order["total"], 2), "currency": "INR",
                "payment_method": order["payment_method"], "payment_status": order["payment_status"],
                "order_status": order["order_status"], "created_at": order["created_at"],
                "items": [{
                    "product_id": item["product_id"], "product_name": item["product_name"],
                    "unit_price": round(item["unit_price"], 2), "quantity": item["quantity"],
                    "line_total": round(item["line_total"], 2),
                } for item in items],
            })
    return output


@app.get("/api/orders/{order_number}")
def get_order(order_number: str) -> dict[str, Any]:
    """Retrieve a demo order confirmation by its order number."""
    with db_connection() as conn:
        order = conn.execute("SELECT * FROM orders WHERE order_number = ?", (order_number,)).fetchone()
        if order is None:
            raise HTTPException(status_code=404, detail="Order not found")
        items = conn.execute(
            "SELECT product_id, product_name, unit_price, quantity, line_total FROM order_items WHERE order_id = ?",
            (order["id"],),
        ).fetchall()
    return {
        "order_number": order["order_number"], "customer_name": order["customer_name"],
        "total": round(order["total"], 2), "currency": "INR",
        "payment_method": order["payment_method"], "payment_status": order["payment_status"],
        "order_status": order["order_status"], "created_at": order["created_at"],
        "message": "This is a demo order. No real payment was taken.",
        "items": [{
            "product_id": item["product_id"], "product_name": item["product_name"],
            "unit_price": round(item["unit_price"], 2),
            "quantity": item["quantity"], "line_total": round(item["line_total"], 2),
        } for item in items],
    }
