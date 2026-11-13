# Shopsika Backend (FastAPI + Groq + SQLite)

This is a standalone backend for an AI shopping agent. The frontend can be generated separately (for example with Claude) and integrated through the JSON REST API described below.

**Demo checkout only:** no real payment is processed. Do not collect real card numbers, CVVs, PINs, or banking credentials. A future Razorpay integration should use its official checkout and server-side payment verification.

## 1. Requirements

- Python 3.10+
- A Groq API key for AI chat (product list and demo order endpoints work without it)

## 2. Setup on Windows

Open a terminal in this folder:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Open `.env` and replace `GROQ_API_KEY` with your own key. Never put this key in frontend code or commit `.env` to Git.

If PowerShell blocks virtual-environment activation, you can use `.venv\Scripts\python.exe -m pip install -r requirements.txt` and `.venv\Scripts\python.exe -m uvicorn main:app --reload` instead.

## 3. Start the API

```powershell
uvicorn main:app --reload
```

On first start, the app creates `shopsika.db` and inserts sample products. API base URL: `http://127.0.0.1:8000`.

### Add or edit demo products

Edit `demo_products.json` in this folder, then restart the backend. Each entry uses a price in rupees, a stock count, and an `image_url` (a direct image URL, or an empty string if you do not have one). On startup, Shopsika syncs the product table to this curated list. Removed products are deleted; order line names and prices remain saved, with the catalog link cleared when needed. Retained products keep their stock counts.

Example entry:

```json
{
  "name": "Demo Phone X",
  "description": "A sample phone for the demo catalog.",
  "category": "Phones",
  "price": 24999,
  "brand": "Demo Brand",
  "specifications": "128 GB storage; 5G; OLED display",
  "stock": 8,
  "image_url": "https://example.com/phone.jpg"
}
```

The catalog initially shows twelve products total. Use **Show more** to reveal the next twelve. The curated catalog has 40 products, at most four distinct product types per category, and excludes bags and home products. The demo catalog is data only; product details, stock, and prices are not verified real-world offers.

- Interactive API docs: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/api/health

## 4. API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Check the API is running |
| GET | `/api/products` | List/search products; supports `q`, `category`, `max_price`, `in_stock`, `limit` |
| GET | `/api/products/{product_id}` | Get one product |
| POST | `/api/chat` | Stateful shopping chat; returns products and persisted checkout state |
| POST | `/api/orders` | Create a confirmed demo order; validates stock and saves it |
| GET | `/api/orders/{order_number}` | Retrieve an order confirmation |

Product prices are stored in rupees in the database and returned as rupees by the API. A generated paise value supports exact integer calculations for orders; order totals and order line snapshots remain stored in paise.

### Example: search products

```powershell
curl.exe "http://127.0.0.1:8000/api/products?q=headphones&max_price=2000"
```

### Example: stateful shopping chat

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/chat" -H "Content-Type: application/json" -d "{\"message\":\"Find wireless headphones under 2000 with a good microphone\"}"
```

Typical response:

```json
{
  "reply": "I found a headphone option that fits your budget...",
  "session_id": "persisted-session-token",
  "order_stage": "shopping",
  "missing_fields": [],
  "requires_confirmation": false,
  "order_summary": null,
  "order_result": null,
  "products": [
    {
      "id": 1,
      "name": "SoundBeat Wireless Headphones",
      "description": "Over-ear wireless headphones with a built-in microphone and long battery life.",
      "category": "Audio",
      "price": 1799.0,
      "brand": "SoundBeat",
      "specifications": "Bluetooth 5.3; up to 35-hour battery; built-in microphone",
      "stock": 18,
      "image_url": "",
      "in_stock": true
    }
  ],
  "mode": "ai"
}
```

The product list depends on the current database and model response; this is only an example.

Send the returned `session_id` on every subsequent chat request. The backend persists the cart and checkout fields in SQLite; `history` remains optional for product discovery. Select a returned product with `select product 1`. The assistant requests a name, phone, and delivery address, asks for the demo payment option, and returns an `order_summary` with `requires_confirmation: true`. Only an explicit `confirm` creates the order. `cancel checkout` clears the pending cart. Never send card, CVV, PIN, or banking details.

Example checkout sequence (reuse the same session ID each time):

```json
{"message":"select product 1"}
{"message":"Demo Customer","session_id":"returned-session-id"}
{"message":"9000000000","session_id":"returned-session-id"}
{"message":"12 Example Road, Kolkata, West Bengal, 700001","session_id":"returned-session-id"}
{"message":"demo payment","session_id":"returned-session-id"}
{"message":"confirm","session_id":"returned-session-id"}
```

Two-request persistence check:

```json
{"message":"find headphones"}
{"message":"My name is Rahul, my phone number is 9000000000, and my delivery address is 10 Park Street, Kolkata.","session_id":"the-session-id-from-the-first-response","history":[]}
```

On the second response, `order_summary` retains the selected item and the supplied name, phone, and address. Its stage becomes `payment_selection` (and `missing_fields` includes only `payment_method`). You may also send `order the first one` with the same session ID and no history; the server resolves it from the saved ordered search results.

Successful confirmation returns the authoritative `order_result` from SQLite. Repeating confirmation for a session returns its existing result and does not create a second order.

### Example: create a demo order

Call this only after the user has reviewed the order summary and explicitly confirmed the demo order. Use product IDs from the API, not product names or prices supplied by the browser. The backend looks up current prices and stock itself.

```json
{
  "customer_name": "Demo Customer",
  "email": "demo@example.com",
  "phone": "9000000000",
  "delivery_address": "12 Example Road, Kolkata, West Bengal, 700001",
  "items": [
    { "product_id": 1, "quantity": 1 }
  ],
  "payment_method": "demo",
  "confirm_demo_order": true
}
```

Example request using JavaScript:

```js
const response = await fetch("http://127.0.0.1:8000/api/orders", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(orderPayload),
});
const data = await response.json();
if (!response.ok) throw new Error(data.detail || "Could not create order");
// Only show success after this response succeeds.
console.log(data.order_number, data.message);
```

A successful response has `payment_status: "demo_not_charged"` and a message saying no real payment was taken. The demo checkout does not request or store card details.

## 5. Frontend integration contract

Configure one frontend environment variable, for example in the React project `.env`:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Use `import.meta.env.VITE_API_BASE_URL` for browser requests. Never expose `GROQ_API_KEY` in a `VITE_` variable.

- Chat: `POST ${API_BASE}/api/chat` with `{ message, history }`
- Product list: `GET ${API_BASE}/api/products?q=...`
- Product details: `GET ${API_BASE}/api/products/{id}`
- Demo order: `POST ${API_BASE}/api/orders`
- Order confirmation: `GET ${API_BASE}/api/orders/{order_number}`

For the chat UI, render `reply` as text and render each entry in `products` as a product card. If no products were found, `products` will be an empty array. For checkout, show a summary from product data, then send product IDs and quantities. Do not trust prices computed in the frontend.

## 6. Testing checklist

1. Start server and open `/docs`.
2. Call `GET /api/health`.
3. Call `GET /api/products` and check sample records.
4. Test product search with `q=headphones` and `max_price=2000`.
5. Test `POST /api/chat`; catalog search has a Python fallback and Groq improves discovery and wording.
6. Walk through chat checkout and confirm only after reviewing `order_summary`.
7. Verify the returned order number with `GET /api/orders/{order_number}`.
8. Try ordering more units than available and verify that the API rejects it.

Run the automated suite with:

```powershell
python -m pip install -r requirements.txt
python -m pytest -q
```

## Notes

- SQLite is ideal for local development and a single-instance demo. For a deployed multi-instance service, use a persistent disk or move to a managed database before launch.
- Product image URLs are blank in seed data. You can add image URLs to the SQLite rows later or build an admin/import flow.
- The Groq model name can change by provider availability. If the configured model is unavailable, choose a currently available Groq model that supports tool calling and update `GROQ_MODEL` in `.env`.
- This is a learning/demo foundation, not production checkout. Before public deployment, add authentication, rate limits, request logging, privacy protections, and stronger order/customer access controls.
