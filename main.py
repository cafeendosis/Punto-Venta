"""API del punto de venta.

The original one-product endpoints remain available.  The additional routes
provide authentication, cash register operations, purchases and reports.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
import schemas
from database import Base, SessionLocal, engine


JWT_SECRET = os.getenv("JWT_SECRET", "cambiar-esta-clave-en-produccion")
JWT_TTL_MINUTES = int(os.getenv("JWT_TTL_MINUTES", "480"))
ALLOWED_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")

app = FastAPI(title="Tienda Abarrotes POS", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in ALLOWED_ORIGINS if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    rounds = 310_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, rounds)
    return f"pbkdf2_sha256${rounds}${salt.hex()}${digest.hex()}"


def _verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt, expected = encoded.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt), int(rounds)
        ).hex()
        return hmac.compare_digest(actual, expected)
    except (TypeError, ValueError):
        return False


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _jwt_encode(payload: dict) -> str:
    header = _b64(b'{"alg":"HS256","typ":"JWT"}')
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    signature = _b64(hmac.new(JWT_SECRET.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest())
    return f"{header}.{body}.{signature}"


def _jwt_decode(token: str) -> dict:
    try:
        header, body, signature = token.split(".")
        expected = _b64(hmac.new(JWT_SECRET.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        padding = "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(body + padding))
        if not isinstance(payload, dict) or "sub" not in payload:
            raise ValueError
        if int(payload.get("exp", 0)) < int(datetime.now(timezone.utc).timestamp()):
            raise ValueError
        return payload
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=401, detail="Token inválido o expirado")


def _upgrade_existing_sqlite_schema() -> None:
    """Add non-destructive columns when upgrading the original SQLite DB."""
    if not str(engine.url).startswith("sqlite"):
        return
    additions = {
        "productos": {
            "categoria": "VARCHAR(100)",
            "stock_minimo": "INTEGER DEFAULT 0",
            "activo": "BOOLEAN DEFAULT 1",
            "creado_en": "DATETIME",
        },
        "lotes": {"proveedor": "VARCHAR(200)"},
        "ventas": {
            "usuario_id": "INTEGER",
            "caja_id": "INTEGER",
            "ticket": "VARCHAR(40)",
            "metodo_pago": "VARCHAR(20) DEFAULT 'efectivo'",
            "total": "FLOAT",
        },
    }
    inspector = inspect(engine)
    with engine.begin() as connection:
        for table, columns in additions.items():
            if not inspector.has_table(table):
                continue
            existing = {column["name"] for column in inspector.get_columns(table)}
            for name, definition in columns.items():
                if name not in existing:
                    connection.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {definition}'))


def init_db() -> None:
    _upgrade_existing_sqlite_schema()
    Base.metadata.create_all(bind=engine)


@app.on_event("startup")
def startup() -> None:
    init_db()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_optional_user(
    db: Session = Depends(get_db), authorization: Optional[str] = Header(default=None)
) -> Optional[models.Usuario]:
    # Kept deliberately optional for backwards compatibility with the initial API.
    if not authorization:
        return None
    token = authorization.removeprefix("Bearer ").strip()
    payload = _jwt_decode(token)
    user = db.get(models.Usuario, int(payload["sub"]))
    if not user or not user.activo:
        raise HTTPException(status_code=401, detail="Usuario inactivo")
    return user


def get_current_user(
    db: Session = Depends(get_db), authorization: Optional[str] = Header(default=None)
) -> models.Usuario:
    if not authorization:
        raise HTTPException(status_code=401, detail="Autenticación requerida")
    token = authorization.removeprefix("Bearer ").strip()
    payload = _jwt_decode(token)
    user = db.get(models.Usuario, int(payload["sub"]))
    if not user or not user.activo:
        raise HTTPException(status_code=401, detail="Usuario inactivo")
    return user


def require_roles(*roles: str):
    def dependency(user: models.Usuario = Depends(get_current_user)):
        if user.rol not in roles:
            raise HTTPException(status_code=403, detail="Permisos insuficientes")
        return user

    return dependency


def stock_total(producto: models.Producto) -> int:
    return sum(max(lote.cantidad, 0) for lote in producto.Lotes)


def producto_response(producto: models.Producto) -> dict:
    return {
        "id": producto.id,
        "codigo_barras": producto.codigo_barras,
        "nombre": producto.nombre,
        "precio_venta": producto.precio_venta,
        "categoria": producto.categoria,
        "stock_minimo": producto.stock_minimo or 0,
        "activo": producto.activo if producto.activo is not None else True,
        "stock_total": stock_total(producto),
    }


def get_open_cash(db: Session, caja_id: int) -> models.Caja:
    caja = db.get(models.Caja, caja_id)
    if not caja or caja.estado != "abierta":
        raise HTTPException(status_code=400, detail="La caja no existe o está cerrada")
    return caja


def cash_balance(caja: models.Caja) -> float:
    return round(
        caja.monto_apertura
        + sum(
            movement.monto if movement.tipo == "ingreso" else -movement.monto
            for movement in caja.movimientos
            if movement.tipo in {"ingreso", "egreso"}
        ),
        2,
    )


@app.get("/health")
def health():
    return {"status": "ok"}


# Authentication -----------------------------------------------------------------
@app.post("/auth/register", response_model=schemas.UsuarioOut)
def register(
    data: schemas.UsuarioCreate,
    db: Session = Depends(get_db),
    current: Optional[models.Usuario] = Depends(get_optional_user),
):
    total_users = db.query(models.Usuario).count()
    if total_users and (not current or current.rol != "admin"):
        raise HTTPException(status_code=403, detail="Solo un administrador puede crear usuarios")
    role = data.rol if total_users else "admin"
    if db.query(models.Usuario).filter(models.Usuario.usuario == data.usuario).first():
        raise HTTPException(status_code=409, detail="El usuario ya existe")
    user = models.Usuario(
        usuario=data.usuario,
        email=data.email,
        password_hash=_hash_password(data.password),
        rol=role,
    )
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Usuario o email ya registrado")
    return user


@app.post("/auth/login")
def login(data: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.Usuario).filter(models.Usuario.usuario == data.usuario).first()
    if not user or not user.activo or not _verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    expires = datetime.now(timezone.utc) + timedelta(minutes=JWT_TTL_MINUTES)
    token = _jwt_encode({"sub": str(user.id), "rol": user.rol, "exp": int(expires.timestamp())})
    return {"access_token": token, "token_type": "bearer", "usuario": schemas.UsuarioOut.model_validate(user)}


@app.get("/auth/me", response_model=schemas.UsuarioOut)
def me(user: models.Usuario = Depends(get_current_user)):
    return user


@app.get("/usuarios", response_model=list[schemas.UsuarioOut])
def listar_usuarios(
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(require_roles("admin", "gerente")),
):
    return db.query(models.Usuario).order_by(models.Usuario.usuario).all()


@app.post("/usuarios", response_model=schemas.UsuarioOut)
def crear_usuario(
    data: schemas.UsuarioCreate,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(require_roles("admin")),
):
    if db.query(models.Usuario).filter(models.Usuario.usuario == data.usuario).first():
        raise HTTPException(status_code=409, detail="El usuario ya existe")
    user = models.Usuario(
        usuario=data.usuario,
        email=data.email,
        password_hash=_hash_password(data.password),
        rol=data.rol,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# Products and inventory ---------------------------------------------------------
@app.post("/productos/", response_model=schemas.ProductoConStock)
def crear_producto(datos: schemas.ProductoCreate, db: Session = Depends(get_db)):
    producto = models.Producto(**datos.model_dump())
    db.add(producto)
    try:
        db.commit()
        db.refresh(producto)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Código de barras ya registrado")
    return producto_response(producto)


@app.get("/productos/{codigo_barras}", response_model=schemas.ProductoConStock)
def obtener_producto(codigo_barras: str, db: Session = Depends(get_db)):
    producto = db.query(models.Producto).filter(models.Producto.codigo_barras == codigo_barras).first()
    if producto is None:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return producto_response(producto)


@app.get("/productos", response_model=list[schemas.ProductoConStock])
def listar_productos(
    buscar: Optional[str] = Query(default=None),
    solo_activos: bool = True,
    db: Session = Depends(get_db),
):
    query = db.query(models.Producto)
    if solo_activos:
        query = query.filter(models.Producto.activo.is_(True))
    if buscar:
        query = query.filter(
            (models.Producto.nombre.ilike(f"%{buscar}%"))
            | (models.Producto.codigo_barras.ilike(f"%{buscar}%"))
        )
    return [producto_response(producto) for producto in query.order_by(models.Producto.nombre).all()]


@app.put("/productos/{codigo_barras}", response_model=schemas.ProductoConStock)
def actualizar_producto(
    codigo_barras: str, datos: schemas.ProductoUpdate, db: Session = Depends(get_db)
):
    producto = db.query(models.Producto).filter(models.Producto.codigo_barras == codigo_barras).first()
    if producto is None:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    for key, value in datos.model_dump(exclude_unset=True).items():
        setattr(producto, key, value)
    db.commit()
    db.refresh(producto)
    return producto_response(producto)


@app.post("/lotes/")
def crear_lote(datos: schemas.LoteCreate, db: Session = Depends(get_db)):
    producto = db.query(models.Producto).filter(models.Producto.codigo_barras == datos.codigo_barras).first()
    if producto is None:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    lote = models.Lote(
        producto_id=producto.id,
        cantidad=datos.cantidad,
        precio_compra=datos.precio_compra,
        proveedor=datos.proveedor,
    )
    db.add(lote)
    db.commit()
    db.refresh(lote)
    return lote


@app.post("/compras/")
def crear_compra(
    data: schemas.CompraCreate,
    db: Session = Depends(get_db),
    user: Optional[models.Usuario] = Depends(get_optional_user),
):
    producto = db.query(models.Producto).filter(models.Producto.codigo_barras == data.codigo_barras).first()
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    total = round(data.cantidad * data.precio_compra, 2)
    caja = get_open_cash(db, data.caja_id) if data.caja_id else None
    compra = models.Compra(
        producto_id=producto.id,
        cantidad=data.cantidad,
        precio_compra=data.precio_compra,
        proveedor=data.proveedor,
        usuario_id=user.id if user else None,
        caja_id=caja.id if caja else None,
        metodo_pago=data.metodo_pago,
        total=total,
    )
    db.add(models.Lote(
        producto_id=producto.id,
        cantidad=data.cantidad,
        precio_compra=data.precio_compra,
        proveedor=data.proveedor,
    ))
    db.add(compra)
    if caja and data.metodo_pago == "efectivo":
        if cash_balance(caja) < total:
            db.rollback()
            raise HTTPException(status_code=400, detail="Saldo insuficiente en caja")
        db.add(models.MovimientoCaja(
            caja_id=caja.id, usuario_id=user.id if user else None, tipo="egreso",
            monto=total, concepto=f"Compra a {data.proveedor or 'proveedor'}",
        ))
    db.commit()
    db.refresh(compra)
    return compra


# Sales --------------------------------------------------------------------------
def _sell_items(
    items: list[schemas.VentaItem],
    caja_id: Optional[int],
    metodo_pago: str,
    efectivo_recibido: Optional[float],
    db: Session,
    user: Optional[models.Usuario],
):
    caja = get_open_cash(db, caja_id) if caja_id else None
    products = []
    total = 0.0
    # Aggregate repeated barcodes so a ticket can never consume the same stock
    # twice after each line independently passed the initial check.
    grouped: dict[str, int] = {}
    for item in items:
        grouped[item.codigo_barras] = grouped.get(item.codigo_barras, 0) + item.cantidad
    for code, quantity in grouped.items():
        item = schemas.VentaItem(codigo_barras=code, cantidad=quantity)
        product = db.query(models.Producto).filter(
            models.Producto.codigo_barras == code,
            models.Producto.activo.is_(True),
        ).first()
        if not product:
            raise HTTPException(status_code=404, detail=f"Producto no encontrado: {code}")
        if stock_total(product) < item.cantidad:
            raise HTTPException(status_code=400, detail=f"Stock insuficiente: {product.nombre}")
        products.append((item, product))
        total += item.cantidad * product.precio_venta
    total = round(total, 2)
    if metodo_pago == "efectivo" and efectivo_recibido is not None and efectivo_recibido < total:
        raise HTTPException(status_code=400, detail="El efectivo recibido es insuficiente")
    if caja and metodo_pago == "efectivo":
        # The sale is an ingreso; non-cash payments are tracked but do not affect cash.
        pass
    ticket = uuid.uuid4().hex[:12].upper()
    rows = []
    for item, product in products:
        remaining = item.cantidad
        for lote in sorted(product.Lotes, key=lambda batch: batch.fecha_ingreso or datetime.min):
            if remaining <= 0:
                break
            consumed = min(lote.cantidad, remaining)
            lote.cantidad -= consumed
            remaining -= consumed
        if remaining:
            db.rollback()
            raise HTTPException(status_code=400, detail=f"Stock insuficiente: {product.nombre}")
        row = models.Venta(
            producto_id=product.id,
            cantidad=item.cantidad,
            precio_venta=product.precio_venta,
            total=round(item.cantidad * product.precio_venta, 2),
            usuario_id=user.id if user else None,
            caja_id=caja.id if caja else None,
            ticket=ticket,
            metodo_pago=metodo_pago,
        )
        db.add(row)
        rows.append(row)
    if caja and metodo_pago == "efectivo":
        db.add(models.MovimientoCaja(
            caja_id=caja.id, usuario_id=user.id if user else None, tipo="ingreso",
            monto=total, concepto=f"Venta {ticket}",
        ))
    db.commit()
    return ticket, total, rows


@app.post("/ventas/")
def crear_venta(
    datos: schemas.VentaCreate,
    db: Session = Depends(get_db),
    user: Optional[models.Usuario] = Depends(get_optional_user),
):
    _, _, rows = _sell_items(
        [schemas.VentaItem(codigo_barras=datos.codigo_barras, cantidad=datos.cantidad)],
        datos.caja_id, datos.metodo_pago, datos.efectivo_recibido, db, user,
    )
    db.refresh(rows[0])
    return rows[0]


@app.post("/ventas/multiple")
def crear_venta_multiple(
    data: schemas.VentaMultipleCreate,
    db: Session = Depends(get_db),
    user: Optional[models.Usuario] = Depends(get_optional_user),
):
    ticket, total, _ = _sell_items(
        data.items, data.caja_id, data.metodo_pago, data.efectivo_recibido, db, user
    )
    change = round((data.efectivo_recibido or 0) - total, 2) if data.metodo_pago == "efectivo" else 0
    return {"ticket": ticket, "total": total, "cambio": max(change, 0)}


@app.get("/ventas")
def listar_ventas(
    desde: Optional[datetime] = None,
    hasta: Optional[datetime] = None,
    db: Session = Depends(get_db),
    _: Optional[models.Usuario] = Depends(get_optional_user),
):
    query = db.query(models.Venta)
    if desde:
        query = query.filter(models.Venta.fecha_venta >= desde)
    if hasta:
        query = query.filter(models.Venta.fecha_venta <= hasta)
    return query.order_by(models.Venta.fecha_venta.desc()).limit(500).all()


# Cash register ------------------------------------------------------------------
@app.get("/cajas/actual")
def caja_actual(
    db: Session = Depends(get_db),
    user: models.Usuario = Depends(get_current_user),
):
    caja = db.query(models.Caja).filter(
        models.Caja.usuario_id == user.id, models.Caja.estado == "abierta"
    ).order_by(models.Caja.abierta_en.desc()).first()
    if not caja:
        return None
    return {
        "id": caja.id, "estado": caja.estado, "monto_apertura": caja.monto_apertura,
        "saldo": cash_balance(caja), "abierta_en": caja.abierta_en,
    }


@app.post("/cajas/abrir")
def abrir_caja(
    data: schemas.CajaAbrir,
    db: Session = Depends(get_db),
    user: models.Usuario = Depends(get_current_user),
):
    if db.query(models.Caja).filter(models.Caja.usuario_id == user.id, models.Caja.estado == "abierta").first():
        raise HTTPException(status_code=400, detail="Ya tienes una caja abierta")
    caja = models.Caja(usuario_id=user.id, monto_apertura=data.monto_apertura, nota=data.nota)
    db.add(caja)
    db.flush()
    db.add(models.MovimientoCaja(
        caja_id=caja.id, usuario_id=user.id, tipo="apertura",
        monto=data.monto_apertura, concepto="Apertura de caja",
    ))
    db.commit()
    db.refresh(caja)
    return {"id": caja.id, "saldo": cash_balance(caja), "estado": caja.estado}


@app.post("/cajas/{caja_id}/movimientos")
def movimiento_caja(
    caja_id: int,
    data: schemas.MovimientoCreate,
    db: Session = Depends(get_db),
    user: models.Usuario = Depends(get_current_user),
):
    if data.tipo not in {"ingreso", "egreso"}:
        raise HTTPException(status_code=400, detail="Tipo debe ser ingreso o egreso")
    caja = get_open_cash(db, caja_id)
    if data.tipo == "egreso" and cash_balance(caja) < data.monto:
        raise HTTPException(status_code=400, detail="Saldo insuficiente en caja")
    movement = models.MovimientoCaja(
        caja_id=caja.id, usuario_id=user.id, tipo=data.tipo,
        monto=data.monto, concepto=data.concepto,
    )
    db.add(movement)
    db.commit()
    return {"id": movement.id, "saldo": cash_balance(caja)}


@app.post("/cajas/{caja_id}/cerrar")
def cerrar_caja(
    caja_id: int,
    data: schemas.CajaCerrar,
    db: Session = Depends(get_db),
    user: models.Usuario = Depends(get_current_user),
):
    caja = get_open_cash(db, caja_id)
    if caja.usuario_id != user.id and user.rol not in {"admin", "gerente"}:
        raise HTTPException(status_code=403, detail="Solo el responsable puede cerrar esta caja")
    expected = cash_balance(caja)
    caja.monto_cierre = data.monto_cierre
    caja.estado = "cerrada"
    caja.cerrada_en = datetime.now(timezone.utc)
    caja.nota = data.nota or caja.nota
    db.add(models.MovimientoCaja(
        caja_id=caja.id, usuario_id=user.id, tipo="cierre",
        monto=data.monto_cierre, concepto=f"Cierre (esperado {expected:.2f})",
    ))
    db.commit()
    return {"id": caja.id, "esperado": expected, "contado": data.monto_cierre,
            "diferencia": round(data.monto_cierre - expected, 2)}


# Reports ------------------------------------------------------------------------
@app.get("/reportes/resumen")
def reporte_resumen(
    desde: Optional[datetime] = None,
    hasta: Optional[datetime] = None,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(require_roles("admin", "gerente", "cajero")),
):
    sales = db.query(models.Venta)
    purchases = db.query(models.Compra)
    if desde:
        sales = sales.filter(models.Venta.fecha_venta >= desde)
        purchases = purchases.filter(models.Compra.fecha_compra >= desde)
    if hasta:
        sales = sales.filter(models.Venta.fecha_venta <= hasta)
        purchases = purchases.filter(models.Compra.fecha_compra <= hasta)
    sale_rows = sales.all()
    purchase_rows = purchases.all()
    products = db.query(models.Producto).all()
    return {
        "ventas": len(sale_rows),
        "total_ventas": round(sum(row.total or row.cantidad * row.precio_venta for row in sale_rows), 2),
        "compras": len(purchase_rows),
        "total_compras": round(sum(row.total or row.cantidad * row.precio_compra for row in purchase_rows), 2),
        "productos": len(products),
        "stock_bajo": [
            {"nombre": product.nombre, "codigo_barras": product.codigo_barras,
             "stock": stock_total(product), "minimo": product.stock_minimo or 0}
            for product in products if stock_total(product) <= (product.stock_minimo or 0)
        ],
    }


@app.get("/reportes/inventario")
def reporte_inventario(
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(require_roles("admin", "gerente", "cajero")),
):
    return [producto_response(product) for product in db.query(models.Producto).order_by(models.Producto.nombre).all()]


@app.get("/reportes/ventas")
def reporte_ventas(
    desde: Optional[datetime] = None,
    hasta: Optional[datetime] = None,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(require_roles("admin", "gerente", "cajero")),
):
    query = db.query(models.Venta)
    if desde:
        query = query.filter(models.Venta.fecha_venta >= desde)
    if hasta:
        query = query.filter(models.Venta.fecha_venta <= hasta)
    rows = query.order_by(models.Venta.fecha_venta.desc()).limit(1000).all()
    return [
        {"id": row.id, "ticket": row.ticket, "producto": row.producto.nombre,
         "cantidad": row.cantidad, "total": row.total or row.cantidad * row.precio_venta,
         "fecha": row.fecha_venta, "metodo_pago": row.metodo_pago}
        for row in rows
    ]
