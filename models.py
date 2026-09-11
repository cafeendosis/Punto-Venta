from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from database import Base


def utcnow():
    return datetime.now(timezone.utc)


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    usuario = Column(String(80), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=True)
    password_hash = Column(String(255), nullable=False)
    rol = Column(String(30), nullable=False, default="cajero")
    activo = Column(Boolean, nullable=False, default=True)
    creado_en = Column(DateTime, default=utcnow, nullable=False)

    cajas = relationship("Caja", back_populates="usuario")
    ventas = relationship("Venta", back_populates="usuario")


class Producto(Base):
    __tablename__ = "productos"

    id = Column(Integer, primary_key=True, index=True)
    codigo_barras = Column(String(100), unique=True, index=True, nullable=False)
    nombre = Column(String(200), index=True, nullable=False)
    precio_venta = Column(Float, nullable=False)
    categoria = Column(String(100), nullable=True)
    stock_minimo = Column(Integer, nullable=False, default=0)
    activo = Column(Boolean, nullable=False, default=True)
    creado_en = Column(DateTime, default=utcnow, nullable=True)

    Lotes = relationship("Lote", back_populates="producto", cascade="all, delete-orphan")
    ventas = relationship("Venta", back_populates="producto")
    compras = relationship("Compra", back_populates="producto")


class Lote(Base):
    __tablename__ = "lotes"

    id = Column(Integer, primary_key=True, index=True)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=False, index=True)
    cantidad = Column(Integer, nullable=False)
    fecha_ingreso = Column(DateTime, default=utcnow)
    precio_compra = Column(Float, nullable=False)
    proveedor = Column(String(200), nullable=True)

    producto = relationship("Producto", back_populates="Lotes")


class Caja(Base):
    __tablename__ = "cajas"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    monto_apertura = Column(Float, nullable=False, default=0)
    monto_cierre = Column(Float, nullable=True)
    estado = Column(String(20), nullable=False, default="abierta")
    abierta_en = Column(DateTime, default=utcnow, nullable=False)
    cerrada_en = Column(DateTime, nullable=True)
    nota = Column(Text, nullable=True)

    usuario = relationship("Usuario", back_populates="cajas")
    movimientos = relationship("MovimientoCaja", back_populates="caja", cascade="all, delete-orphan")
    ventas = relationship("Venta", back_populates="caja")
    compras = relationship("Compra", back_populates="caja")


class MovimientoCaja(Base):
    __tablename__ = "movimientos_caja"

    id = Column(Integer, primary_key=True, index=True)
    caja_id = Column(Integer, ForeignKey("cajas.id"), nullable=False, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    tipo = Column(String(20), nullable=False)  # ingreso, egreso, apertura, cierre
    monto = Column(Float, nullable=False)
    concepto = Column(String(255), nullable=False)
    creado_en = Column(DateTime, default=utcnow, nullable=False)

    caja = relationship("Caja", back_populates="movimientos")


class Venta(Base):
    __tablename__ = "ventas"

    id = Column(Integer, primary_key=True, index=True)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=False)
    cantidad = Column(Integer, nullable=False)
    fecha_venta = Column(DateTime, default=utcnow)
    precio_venta = Column(Float, nullable=False)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    caja_id = Column(Integer, ForeignKey("cajas.id"), nullable=True)
    ticket = Column(String(40), index=True, nullable=True)
    metodo_pago = Column(String(20), default="efectivo", nullable=False)
    total = Column(Float, nullable=True)

    producto = relationship("Producto", back_populates="ventas")
    usuario = relationship("Usuario", back_populates="ventas")
    caja = relationship("Caja", back_populates="ventas")


class Compra(Base):
    __tablename__ = "compras"

    id = Column(Integer, primary_key=True, index=True)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=False)
    cantidad = Column(Integer, nullable=False)
    precio_compra = Column(Float, nullable=False)
    proveedor = Column(String(200), nullable=True)
    fecha_compra = Column(DateTime, default=utcnow, nullable=False)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    caja_id = Column(Integer, ForeignKey("cajas.id"), nullable=True)
    metodo_pago = Column(String(20), default="efectivo", nullable=False)
    total = Column(Float, nullable=True)

    producto = relationship("Producto", back_populates="compras")
    caja = relationship("Caja", back_populates="compras")
