from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from database import SessionLocal
import models
import schemas

app = FastAPI()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.post("/productos/")
def crear_producto(datos: schemas.ProductoCreate, db: Session = Depends(get_db)):
    producto = models.Producto(
        codigo_barras=datos.codigo_barras,
        nombre=datos.nombre,
        precio_venta=datos.precio_venta
    )
    db.add(producto)
    db.commit()
    db.refresh(producto)
    return producto

@app.get("/productos/{codigo_barras}")
def obtener_producto(codigo_barras: str, db: Session = Depends(get_db)):
    producto = db.query(models.Producto).filter(
        models.Producto.codigo_barras == codigo_barras
        ).first()
    if producto is None:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return producto

@app.post("/lotes/")
def crear_lote(datos: schemas.LoteCreate, db: Session = Depends(get_db)):
    producto = db.query(models.Producto).filter(
        models.Producto.codigo_barras == datos.codigo_barras
        ).first()
    if producto is None:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    lote = models.Lote(
        producto_id=producto.id,
        cantidad=datos.cantidad,
        precio_compra=datos.precio_compra
    )
    db.add(lote)
    db.commit()
    db.refresh(lote)
    return lote

@app.post("/ventas/")
def crear_venta(datos: schemas.VentaCreate, db: Session = Depends(get_db)):
    producto = db.query(models.Producto).filter(
        models.Producto.codigo_barras == datos.codigo_barras
        ).first()
    if producto is None:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    
    # Verificar si hay suficiente stock
    total_stock = sum(lote.cantidad for lote in producto.Lotes)
    if total_stock < datos.cantidad:
        raise HTTPException(status_code=400, detail="Stock insuficiente")
    
    # Crear la venta
    venta = models.Venta(
        producto_id=producto.id,
        cantidad=datos.cantidad,
        precio_venta=producto.precio_venta
    )
    db.add(venta)
    
    # Actualizar los lotes para reflejar la venta
    cantidad_a_vender = datos.cantidad
    for lote in sorted(producto.Lotes, key=lambda x: x.fecha_ingreso):
        if cantidad_a_vender <= 0:
            break
        if lote.cantidad >= cantidad_a_vender:
            lote.cantidad -= cantidad_a_vender
            cantidad_a_vender = 0
        else:
            cantidad_a_vender -= lote.cantidad
            lote.cantidad = 0
    
    db.commit()
    db.refresh(venta)
    return venta

@app.get("/productos", response_model=list[schemas.ProductoConStock])
def listar_productos(db: Session = Depends(get_db)):
    productos = db.query(models.Producto).all()

    resultado = []
    for producto in productos:
        stock_total = sum(lote.cantidad for lote in producto.Lotes)
        producto_con_stock = schemas.ProductoConStock(
            id=producto.id,
            codigo_barras=producto.codigo_barras,
            nombre=producto.nombre,
            precio_venta=producto.precio_venta,
            stock_total=stock_total
        )
        resultado.append(producto_con_stock)
    return resultado


@app.put("/productos/{codigo_barras}")
def actualizar_producto(codigo_barras: str, datos: schemas.ProductoUpdate, db: Session = Depends(get_db)):
    producto = db.query(models.Producto).filter(
        models.Producto.codigo_barras == codigo_barras
        ).first()
    if producto is None:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    
    if datos.nombre is not None:
        producto.nombre = datos.nombre
    if datos.precio_venta is not None:
        producto.precio_venta = datos.precio_venta
    
    db.commit()
    db.refresh(producto)
    return producto 