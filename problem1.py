from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, validator, Field
from enum import Enum
from decimal import Decimal
from typing import List, Optional
import re

app = FastAPI(title="Restaurant Food Ordering System")

menu_db = {}
next_id = 1

class FoodCategory(str, Enum):
    APPETIZER = "appetizer"
    MAIN_COURSE = "main_course"
    DESSERT = "dessert"
    BEVERAGE = "beverage"
    SALAD = "salad"

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

@app.get("/menu")
def get_all_menu_items():
    return list(menu_db.values())

@app.get("/menu/{item_id}")
def get_menu_item(item_id: int):
    if item_id not in menu_db:
        raise HTTPException(status_code=404, detail="Item not found")
    return menu_db[item_id]

@app.post("/menu")
def add_menu_item(item: FoodItem):
    global next_id
    item.id = next_id
    menu_db[next_id] = item
    next_id += 1
    return item

@app.put("/menu/{item_id}")
def update_menu_item(item_id: int, item: FoodItem):
    if item_id not in menu_db:
        raise HTTPException(status_code=404, detail="Item not found")
    item.id = item_id
    menu_db[item_id] = item
    return item

@app.delete("/menu/{item_id}")
def delete_menu_item(item_id: int):
    if item_id not in menu_db:
        raise HTTPException(status_code=404, detail="Item not found")
    deleted_item = menu_db.pop(item_id)
    return {"message": "Item deleted successfully", "deleted_item": deleted_item}

@app.get("/menu/category/{category}")
def get_items_by_category(category: FoodCategory):
    items = [item for item in menu_db.values() if item.category == category]
    return items

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)