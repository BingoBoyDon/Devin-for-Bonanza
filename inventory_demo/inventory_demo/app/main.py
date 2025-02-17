from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Optional
from fastapi.responses import JSONResponse

app = FastAPI(title="Sistema de Inventario")

origins = ["https://test-app-nj243y1q.devinapps.com"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)

class Product(BaseModel):
    name: str
    quantity: int
    description: Optional[str] = None

inventory: Dict[int, Product] = {}

@app.options("/{path:path}")
async def preflight_handler(path: str):
    return JSONResponse(
        content={},
        headers={
            "Access-Control-Allow-Origin": "https://test-app-nj243y1q.devinapps.com",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Max-Age": "3600",
        },
    )

@app.post("/products/")
def create_product(product: Product):
    product_id = len(inventory) + 1
    inventory[product_id] = product
    return product

@app.get("/products/{product_id}")
def get_product(product_id: int):
    if product_id not in inventory:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return inventory[product_id]

@app.get("/products/")
def list_products():
    return inventory

@app.put("/products/{product_id}")
def update_product(product_id: int, product: Product):
    if product_id not in inventory:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    inventory[product_id] = product
    return product

@app.delete("/products/{product_id}")
def delete_product(product_id: int):
    if product_id not in inventory:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    del inventory[product_id]
    return {"message": "Producto eliminado"}
