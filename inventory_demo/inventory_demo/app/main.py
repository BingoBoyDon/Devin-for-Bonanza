from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Optional

app = FastAPI(title="Sistema de Inventario")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Temporarily allow all origins for testing
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Product(BaseModel):
    name: str
    quantity: int
    description: Optional[str] = None

inventory: Dict[int, Product] = {}

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
