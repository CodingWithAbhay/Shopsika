import os
import unittest
from pathlib import Path
import secrets
import json

from fastapi.testclient import TestClient


class ShoppingWorkflowTests(unittest.TestCase):
    def setUp(self):
        test_dir = Path(__file__).resolve().parent / ".testdata"
        test_dir.mkdir(exist_ok=True)
        self.db_path = test_dir / f"test-{secrets.token_hex(4)}.db"
        os.environ["DATABASE_PATH"] = str(self.db_path)
        os.environ.pop("GROQ_API_KEY", None)
        import database
        database.DB_PATH = Path(os.environ["DATABASE_PATH"])
        database.init_db()
        import main
        self.client_context = TestClient(main.app)
        self.client = self.client_context.__enter__()

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        for suffix in ("", "-wal", "-shm"):
            path = Path(str(self.db_path) + suffix)
            if path.exists():
                path.unlink()

    def chat(self, message, session_id=None, history=None):
        data = {"message": message}
        if session_id:
            data["session_id"] = session_id
        if history is not None:
            data["history"] = history
        response = self.client.post("/api/chat", json=data)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_full_order_requires_confirmation_and_is_idempotent(self):
        state = self.chat("select product 1")
        sid = state["session_id"]
        self.assertEqual(state["order_stage"], "collecting_details")
        self.assertIn("customer_name", state["missing_fields"])
        state = self.chat("Demo Customer", sid)
        state = self.chat("9000000000", sid)
        state = self.chat("12 Example Road, Kolkata, West Bengal, 700001", sid)
        self.assertEqual(state["order_stage"], "payment_selection")
        state = self.chat("demo payment", sid)
        self.assertTrue(state["requires_confirmation"])
        self.assertIsNone(state["order_result"])
        state = self.chat("confirm", sid)
        self.assertEqual(state["order_stage"], "order_placed")
        self.assertIsNotNone(state["order_result"])
        order_number = state["order_result"]["order_number"]
        state = self.chat("confirm", sid)
        self.assertEqual(state["order_result"]["order_number"], order_number)
        with __import__("database").db_connection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0], 1)

    def test_cancel_clears_cart_without_order(self):
        state = self.chat("select product 1")
        state = self.chat("cancel checkout", state["session_id"])
        self.assertEqual(state["order_stage"], "shopping")
        self.assertEqual(state["order_summary"], None)
        with __import__("database").db_connection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0], 0)

    def test_product_search_works_without_groq(self):
        state = self.chat("find headphones")
        self.assertTrue(state["products"])
        self.assertEqual(state["products"][0]["name"], "SoundBeat Wireless Headphones")

    def test_search_result_order_persists_and_first_one_selects_without_history(self):
        state = self.chat("find headphones")
        sid = state["session_id"]
        with __import__("database").db_connection() as conn:
            saved = conn.execute("SELECT search_product_ids FROM shopping_sessions WHERE session_id=?", (sid,)).fetchone()
            self.assertEqual(json.loads(saved["search_product_ids"]), [p["id"] for p in state["products"]])
        state = self.chat("I want to order the first one", sid)
        self.assertEqual(state["order_stage"], "collecting_details")
        self.assertEqual(state["order_summary"]["items"][0]["product_id"], 1)

    def test_each_catalog_product_can_be_ordered_by_name_then_contextual_reference(self):
        with __import__("database").db_connection() as conn:
            products = conn.execute("SELECT id,name,stock FROM products WHERE is_active=1 AND stock>0").fetchall()
        self.assertTrue(products)
        for product in products:
            with self.subTest(product=product["name"]):
                detail_query = f"Tell me about {product['name']}"
                state = self.chat(detail_query)
                self.assertEqual([item["id"] for item in state["products"]], [product["id"]])
                state = self.chat(
                    "I want to order this product",
                    state["session_id"],
                    history=[{"role": "user", "content": detail_query}],
                )
                self.assertEqual(state["order_stage"], "quantity_selection")
                self.assertEqual(state["order_summary"]["items"][0]["product_id"], product["id"])

    def test_unresolved_order_request_does_not_return_random_products(self):
        state = self.chat("I want to order this product")
        self.assertEqual(state["order_stage"], "shopping")
        self.assertEqual(state["products"], [])
        self.assertIn("Which catalog product", state["reply"])

    def test_multiple_details_persist_with_empty_history_and_can_be_corrected(self):
        state = self.chat("find headphones")
        sid = state["session_id"]
        self.chat("order the first one", sid)
        state = self.chat("My name is Rahul, my phone number is 9000000000, and my delivery address is 10 Park Street, Kolkata.", sid)
        self.assertEqual(state["order_stage"], "payment_selection")
        self.assertEqual(state["missing_fields"], ["payment_method"])
        state = self.chat("My name is Rohan", sid)
        self.assertEqual(state["order_summary"]["customer_name"], "Rohan")
        self.assertEqual(state["order_summary"]["phone"], "9000000000")
        self.assertIn("10 Park Street", state["order_summary"]["delivery_address"])

    def test_details_and_demo_payment_survive_requests(self):
        state = self.chat("select product ID 1")
        sid = state["session_id"]
        self.chat("My name is Rahul, phone number is 9000000000, delivery address is 10 Park Street, Kolkata", sid)
        state = self.chat("demo payment", sid)
        self.assertTrue(state["requires_confirmation"])
        self.assertEqual(state["order_summary"]["payment_method"], "demo")

    def test_order_requires_confirmation_then_retrieves(self):
        state = self.chat("select product ID 1")
        sid = state["session_id"]
        self.chat("My name is Rahul, phone number is 9000000000, delivery address is 10 Park Street, Kolkata", sid)
        state = self.chat("demo payment", sid)
        self.assertIsNone(state["order_result"])
        state = self.chat("confirm", sid)
        number = state["order_result"]["order_number"]
        self.assertEqual(state["order_stage"], "order_placed")
        self.assertEqual(self.client.get(f"/api/orders/{number}").status_code, 200)
        self.chat("confirm", sid)
        with __import__("database").db_connection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0], 1)

    def test_explicit_invalid_product_does_not_select(self):
        state = self.chat("select product ID 999999")
        self.assertEqual(state["order_stage"], "shopping")
        self.assertIsNone(state["order_summary"])

    def test_order_summary_uses_current_database_price_and_missing_fields_are_accurate(self):
        state = self.chat("select product ID 1")
        sid = state["session_id"]
        self.assertEqual(state["missing_fields"], ["customer_name", "phone", "delivery_address", "payment_method"])
        with __import__("database").db_connection() as conn:
            conn.execute("UPDATE products SET price=1999 WHERE id=1")
        state = self.chat("My name is Rahul, phone number is 9000000000, delivery address is 10 Park Street, Kolkata", sid)
        self.assertEqual(state["order_summary"]["items"][0]["unit_price"], 1999.0)

    def test_insufficient_stock_rejects_confirmation_without_order(self):
        state = self.chat("select product ID 1")
        sid = state["session_id"]
        with __import__("database").db_connection() as conn:
            conn.execute("UPDATE products SET stock=0 WHERE id=1")
        self.chat("My name is Rahul, phone number is 9000000000, delivery address is 10 Park Street, Kolkata", sid)
        self.chat("demo payment", sid)
        state = self.chat("confirm", sid)
        self.assertIsNone(state["order_result"])
        self.assertIn("Not enough stock", state["reply"])
        with __import__("database").db_connection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
