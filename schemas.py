from pydantic import BaseModel

class ProductoCreate(BaseModel):
    codigo_barras: str
    nombre: str
    precio_venta:float

class LoteCreate(BaseModel):
    codigo_barras: str
    cantidad: int
    precio_compra: float 

class VentaCreate(BaseModel):
    codigo_barras: str
    cantidad: int


class ProductoConStock(BaseModel):
    id: int
    codigo_barras: str
    nombre: str
    precio_venta: float
    stock_total: int

    class Config:
        from_attributes = True

class ProductoUpdate(BaseModel):
    nombre: str
    precio_venta: float