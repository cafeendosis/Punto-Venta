from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProductoCreate(BaseModel):
    codigo_barras: str = Field(min_length=1, max_length=100)
    nombre: str = Field(min_length=1, max_length=200)
    precio_venta: float = Field(gt=0)
    categoria: Optional[str] = Field(default=None, max_length=100)
    stock_minimo: int = Field(default=0, ge=0)


class ProductoUpdate(BaseModel):
    nombre: Optional[str] = Field(default=None, min_length=1, max_length=200)
    precio_venta: Optional[float] = Field(default=None, gt=0)
    categoria: Optional[str] = Field(default=None, max_length=100)
    stock_minimo: Optional[int] = Field(default=None, ge=0)
    activo: Optional[bool] = None


class LoteCreate(BaseModel):
    codigo_barras: str = Field(min_length=1)
    cantidad: int = Field(gt=0)
    precio_compra: float = Field(ge=0)
    proveedor: Optional[str] = Field(default=None, max_length=200)
    caja_id: Optional[int] = None


class VentaCreate(BaseModel):
    codigo_barras: str = Field(min_length=1)
    cantidad: int = Field(gt=0)
    caja_id: Optional[int] = None
    metodo_pago: str = "efectivo"
    efectivo_recibido: Optional[float] = Field(default=None, ge=0)


class VentaItem(BaseModel):
    codigo_barras: str = Field(min_length=1)
    cantidad: int = Field(gt=0)


class VentaMultipleCreate(BaseModel):
    items: list[VentaItem] = Field(min_length=1)
    caja_id: Optional[int] = None
    metodo_pago: str = "efectivo"
    efectivo_recibido: Optional[float] = Field(default=None, ge=0)


class CompraCreate(BaseModel):
    codigo_barras: str = Field(min_length=1)
    cantidad: int = Field(gt=0)
    precio_compra: float = Field(ge=0)
    proveedor: Optional[str] = Field(default=None, max_length=200)
    caja_id: Optional[int] = None
    metodo_pago: str = "efectivo"


class ProductoConStock(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    codigo_barras: str
    nombre: str
    precio_venta: float
    categoria: Optional[str] = None
    stock_minimo: int = 0
    activo: bool = True
    stock_total: int


class UsuarioCreate(BaseModel):
    usuario: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=8, max_length=128)
    email: Optional[str] = None
    rol: str = "cajero"

    @field_validator("rol")
    @classmethod
    def valid_role(cls, value: str) -> str:
        if value not in {"admin", "gerente", "cajero"}:
            raise ValueError("rol inválido")
        return value


class LoginRequest(BaseModel):
    usuario: str
    password: str


class UsuarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    usuario: str
    email: Optional[str]
    rol: str
    activo: bool


class CajaAbrir(BaseModel):
    monto_apertura: float = Field(ge=0)
    nota: Optional[str] = None


class CajaCerrar(BaseModel):
    monto_cierre: float = Field(ge=0)
    nota: Optional[str] = None


class MovimientoCreate(BaseModel):
    tipo: str
    monto: float = Field(gt=0)
    concepto: str = Field(min_length=1, max_length=255)


class ReporteFiltros(BaseModel):
    desde: Optional[datetime] = None
    hasta: Optional[datetime] = None
