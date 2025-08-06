from fastapi import FastAPI, HTTPException, Query, Path
from fastapi.responses import JSONResponse
from pydantic import BaseModel, validator, Field
from enum import Enum
from decimal import Decimal
from typing import List, Optional, Dict
import re
import uvicorn

app = FastAPI(
    title="Restaurant Ordering System",
    description="API for managing restaurant menu and orders",
    version="1.0.0"
)

menu_db = {}
orders_db = {}
next_menu_id = 1
next_order_id = 1

class FoodCategory(str, Enum):
    APPETIZER = "appetizer"
    MAIN_COURSE = "main_course"
    DESSERT = "dessert"
    BEVERAGE = "beverage"
    SALAD = "salad"

class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    READY = "ready"
    DELIVERED = "delivered"

class FoodItem(BaseModel):
    id: Optional[int] = None
    name: str = Field(..., min_length=3, max_length=100)
    description: str = Field(..., min_length=10, max_length=500)
    category: FoodCategory
    price: Decimal = Field(..., decimal_places=2)
    is_available: bool = True
    preparation_time: int = Field(..., ge=1, le=120)
    ingredients: List[str] = Field(..., min_items=1)
    calories: Optional[int] = Field(None, gt=0)
    is_vegetarian: bool = False
    is_spicy: bool = False

    @validator('name')
    def validate_name(cls, v):
        if not re.match(r'^[a-zA-Z\s]+$', v):
            raise ValueError('Name should only contain letters and spaces')
        return v

    @validator('price')
    def validate_price(cls, v):
        if v < Decimal('1.00') or v > Decimal('100.00'):
            raise ValueError('Price must be between $1.00 and $100.00')
        return v

    @validator('is_spicy')
    def validate_spicy(cls, v, values):
        if v and values.get('category') in [FoodCategory.DESSERT, FoodCategory.BEVERAGE]:
            raise ValueError('Desserts and beverages cannot be spicy')
        return v

    @validator('calories')
    def validate_calories(cls, v, values):
        if v and values.get('is_vegetarian') and v >= 800:
            raise ValueError('Vegetarian items should have calories < 800')
        return v

    @validator('preparation_time')
    def validate_prep_time(cls, v, values):
        if values.get('category') == FoodCategory.BEVERAGE and v > 10:
            raise ValueError('Beverages should have preparation time ≤ 10 minutes')
        return v

    @property
    def price_category(self) -> str:
        if self.price < 10:
            return "Budget"
        elif self.price <= 25:
            return "Mid-range"
        else:
            return "Premium"

    @property
    def dietary_info(self) -> List[str]:
        info = []
        if self.is_vegetarian:
            info.append("Vegetarian")
        if self.is_spicy:
            info.append("Spicy")
        return info

class OrderItem(BaseModel):
    menu_item_id: int = Field(..., gt=0)
    menu_item_name: str = Field(..., min_length=1, max_length=100)
    quantity: int = Field(..., gt=0, le=10)
    unit_price: Decimal = Field(..., gt=0, max_digits=6, decimal_places=2)

    @property
    def item_total(self) -> Decimal:
        return self.quantity * self.unit_price

class Customer(BaseModel):
    name: str = Field(..., min_length=2, max_length=50)
    phone: str = Field(..., regex=r'^\d{10}$')
    address: Optional[str] = Field(None, max_length=200)

class Order(BaseModel):
    id: Optional[int] = None
    customer: Customer
    items: List[OrderItem] = Field(..., min_items=1)
    status: OrderStatus = OrderStatus.PENDING
    delivery_fee: Decimal = Field(default=Decimal('2.99'), decimal_places=2)
    special_instructions: Optional[str] = Field(None, max_length=200)

    @property
    def items_total(self) -> Decimal:
        return sum(item.item_total for item in self.items)

    @property
    def total_amount(self) -> Decimal:
        return self.items_total + self.delivery_fee

    @property
    def total_items_count(self) -> int:
        return sum(item.quantity for item in self.items)

class FoodItemResponse(BaseModel):
    id: int
    name: str
    description: str
    category: FoodCategory
    price: Decimal
    is_available: bool
    preparation_time: int
    ingredients: List[str]
    calories: Optional[int]
    is_vegetarian: bool
    is_spicy: bool
    price_category: str
    dietary_info: List[str]

class OrderResponse(BaseModel):
    id: int
    customer: Customer
    items: List[OrderItem]
    status: OrderStatus
    delivery_fee: Decimal
    special_instructions: Optional[str]
    items_total: Decimal
    total_amount: Decimal
    total_items_count: int

class OrderSummaryResponse(BaseModel):
    id: int
    customer_name: str
    status: OrderStatus
    total_amount: Decimal
    total_items_count: int

class ErrorResponse(BaseModel):
    error: str
    detail: str

class StatusUpdateRequest(BaseModel):
    status: OrderStatus

@app.exception_handler(422)
async def validation_exception_handler(request, exc):
    return JSONResponse(
        status_code=422,
        content={"error": "Validation Error", "detail": str(exc)}
    )

@app.get("/menu", response_model=List[FoodItemResponse])
def get_all_menu_items():
    return [
        FoodItemResponse(
            id=item.id,
            name=item.name,
            description=item.description,
            category=item.category,
            price=item.price,
            is_available=item.is_available,
            preparation_time=item.preparation_time,
            ingredients=item.ingredients,
            calories=item.calories,
            is_vegetarian=item.is_vegetarian,
            is_spicy=item.is_spicy,
            price_category=item.price_category,
            dietary_info=item.dietary_info
        )
        for item in menu_db.values()
    ]

@app.get("/menu/{item_id}", response_model=FoodItemResponse)
def get_menu_item(item_id: int = Path(..., gt=0)):
    if item_id not in menu_db:
        raise HTTPException(status_code=404, detail="Menu item not found")
    
    item = menu_db[item_id]
    return FoodItemResponse(
        id=item.id,
        name=item.name,
        description=item.description,
        category=item.category,
        price=item.price,
        is_available=item.is_available,
        preparation_time=item.preparation_time,
        ingredients=item.ingredients,
        calories=item.calories,
        is_vegetarian=item.is_vegetarian,
        is_spicy=item.is_spicy,
        price_category=item.price_category,
        dietary_info=item.dietary_info
    )

@app.post("/menu", response_model=FoodItemResponse, status_code=201)
def add_menu_item(item: FoodItem):
    global next_menu_id
    item.id = next_menu_id
    menu_db[next_menu_id] = item
    next_menu_id += 1
    
    return FoodItemResponse(
        id=item.id,
        name=item.name,
        description=item.description,
        category=item.category,
        price=item.price,
        is_available=item.is_available,
        preparation_time=item.preparation_time,
        ingredients=item.ingredients,
        calories=item.calories,
        is_vegetarian=item.is_vegetarian,
        is_spicy=item.is_spicy,
        price_category=item.price_category,
        dietary_info=item.dietary_info
    )

@app.put("/menu/{item_id}", response_model=FoodItemResponse)
def update_menu_item(item_id: int, item: FoodItem):
    if item_id not in menu_db:
        raise HTTPException(status_code=404, detail="Menu item not found")
    
    item.id = item_id
    menu_db[item_id] = item
    
    return FoodItemResponse(
        id=item.id,
        name=item.name,
        description=item.description,
        category=item.category,
        price=item.price,
        is_available=item.is_available,
        preparation_time=item.preparation_time,
        ingredients=item.ingredients,
        calories=item.calories,
        is_vegetarian=item.is_vegetarian,
        is_spicy=item.is_spicy,
        price_category=item.price_category,
        dietary_info=item.dietary_info
    )

@app.delete("/menu/{item_id}")
def delete_menu_item(item_id: int):
    if item_id not in menu_db:
        raise HTTPException(status_code=404, detail="Menu item not found")
    
    deleted_item = menu_db.pop(item_id)
    return {"message": "Menu item deleted successfully", "deleted_item_id": item_id}

@app.get("/menu/category/{category}", response_model=List[FoodItemResponse])
def get_items_by_category(category: FoodCategory):
    items = [item for item in menu_db.values() if item.category == category]
    return [
        FoodItemResponse(
            id=item.id,
            name=item.name,
            description=item.description,
            category=item.category,
            price=item.price,
            is_available=item.is_available,
            preparation_time=item.preparation_time,
            ingredients=item.ingredients,
            calories=item.calories,
            is_vegetarian=item.is_vegetarian,
            is_spicy=item.is_spicy,
            price_category=item.price_category,
            dietary_info=item.dietary_info
        )
        for item in items
    ]

@app.post("/orders", response_model=OrderResponse, status_code=201)
def create_order(order: Order):
    global next_order_id
    
    for item in order.items:
        if item.menu_item_id not in menu_db:
            raise HTTPException(
                status_code=400, 
                detail=f"Menu item with ID {item.menu_item_id} not found"
            )
        
        menu_item = menu_db[item.menu_item_id]
        if not menu_item.is_available:
            raise HTTPException(
                status_code=400, 
                detail=f"Menu item '{menu_item.name}' is not available"
            )
    
    order.id = next_order_id
    orders_db[next_order_id] = order
    next_order_id += 1
    
    return OrderResponse(
        id=order.id,
        customer=order.customer,
        items=order.items,
        status=order.status,
        delivery_fee=order.delivery_fee,
        special_instructions=order.special_instructions,
        items_total=order.items_total,
        total_amount=order.total_amount,
        total_items_count=order.total_items_count
    )

@app.get("/orders", response_model=List[OrderSummaryResponse])
def get_all_orders():
    return [
        OrderSummaryResponse(
            id=order.id,
            customer_name=order.customer.name,
            status=order.status,
            total_amount=order.total_amount,
            total_items_count=order.total_items_count
        )
        for order in orders_db.values()
    ]

@app.get("/orders/{order_id}", response_model=OrderResponse)
def get_order_details(order_id: int = Path(..., gt=0)):
    if order_id not in orders_db:
        raise HTTPException(status_code=404, detail="Order not found")
    
    order = orders_db[order_id]
    return OrderResponse(
        id=order.id,
        customer=order.customer,
        items=order.items,
        status=order.status,
        delivery_fee=order.delivery_fee,
        special_instructions=order.special_instructions,
        items_total=order.items_total,
        total_amount=order.total_amount,
        total_items_count=order.total_items_count
    )

@app.put("/orders/{order_id}/status", response_model=OrderResponse)
def update_order_status(order_id: int, status_update: StatusUpdateRequest):
    if order_id not in orders_db:
        raise HTTPException(status_code=404, detail="Order not found")
    
    order = orders_db[order_id]
    order.status = status_update.status
    
    return OrderResponse(
        id=order.id,
        customer=order.customer,
        items=order.items,
        status=order.status,
        delivery_fee=order.delivery_fee,
        special_instructions=order.special_instructions,
        items_total=order.items_total,
        total_amount=order.total_amount,
        total_items_count=order.total_items_count
    )

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)