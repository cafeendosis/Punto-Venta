from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from database import Base

class Producto(Base):
    __tablename__ = "productos"

    id = Column(Integer, primary_key=True, index=True)
    codigo_barras = Column(String, unique=True, index=True, nullable=False)
    nombre = Column(String, index=True, nullable=False)
    precio_venta = Column(Float, nullable=False)

    Lotes = relationship("Lote", back_populates="producto")

class Lote(Base):
    __tablename__ = "lotes"

    id = Column(Integer, primary_key=True, index=True)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=False)
    cantidad = Column(Integer, nullable=False)
    fecha_ingreso = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    precio_compra = Column(Float, nullable=False)

    producto = relationship("Producto", back_populates="Lotes")

class Venta(Base):
    __tablename__ = "ventas"

    id = Column(Integer, primary_key=True, index=True)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=False)
    cantidad = Column(Integer, nullable=False)
    fecha_venta = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    precio_venta = Column(Float, nullable=False)

    producto = relationship("Producto")


