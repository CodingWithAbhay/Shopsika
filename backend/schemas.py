"""Request and response schemas. Prices are returned in INR rupees for the UI."""
from typing import Any, Literal
from pydantic import BaseModel, Field, ConfigDict


class ProductOut(BaseModel):
    id: int
    name: str
    description: str
    category: str
    price: float
    brand: str
    specifications: str
    stock: int
    image_url: str
    rating: float = Field(ge=0, le=5)
    in_stock: bool

    model_config = ConfigDict(from_attributes=True)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = Field(default=None, min_length=8, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    # Send recent user/assistant text turns from the frontend. Do not send tool messages.
    history: list[dict[str, str]] = Field(default_factory=list, max_length=20)


class ChatResponse(BaseModel):
    reply: str
    products: list[ProductOut] = Field(default_factory=list)
    mode: Literal["ai", "fallback"] = "ai"
    session_id: str | None = None
    order_stage: str = "shopping"
    missing_fields: list[str] = Field(default_factory=list)
    requires_confirmation: bool = False
    order_summary: dict[str, Any] | None = None
    order_result: dict[str, Any] | None = None


class AccountSignUp(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=128)


class AccountSignIn(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class OrderItemIn(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=10)


class OrderCreate(BaseModel):
    customer_name: str = Field(min_length=2, max_length=100)
    email: str = Field(default="", max_length=254)
    phone: str = Field(min_length=7, max_length=25)
    delivery_address: str = Field(min_length=8, max_length=500)
    items: list[OrderItemIn] = Field(min_length=1, max_length=20)
    payment_method: Literal["demo"] = "demo"
    confirm_demo_order: bool = Field(description="Must be true after the user confirms the demo order")


class OrderItemOut(BaseModel):
    product_id: int | None
    product_name: str
    unit_price: float
    quantity: int
    line_total: float


class OrderOut(BaseModel):
    order_number: str
    customer_name: str
    total: float
    currency: str = "INR"
    payment_method: str
    payment_status: str
    order_status: str
    message: str
    items: list[OrderItemOut]
