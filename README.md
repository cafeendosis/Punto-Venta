# Abarrotes POS

Sistema de punto de venta para una tienda de abarrotes: usuarios con roles,
inventario por lotes (FIFO), compras, ventas, caja y reportes. El backend es
FastAPI + SQLAlchemy y el frontend es React + Vite.

## Backend

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export JWT_SECRET='una-clave-larga-y-aleatoria'
uvicorn main:app --reload
```

La API queda en `http://localhost:8000` y la documentación en `/docs`.
`DATABASE_URL` permite usar otra base de datos; por defecto es `sqlite:///./tienda.db`.
El archivo de base de datos, entornos virtuales y secretos están excluidos de Git.

El primer usuario registrado se convierte en `admin`:

```bash
curl -X POST http://localhost:8000/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"usuario":"admin","password":"cambia-esta-clave"}'
```

Después usa `POST /auth/login` para obtener el JWT. Las rutas de caja, compras y
reportes requieren `Authorization: Bearer <token>`. Los endpoints originales
`/productos/`, `/lotes/` y `/ventas/` continúan disponibles.

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Vite sirve la aplicación en `http://localhost:5173`. Para otra URL de API:
`VITE_API_URL=http://localhost:8000 npm run dev`.

La interfaz incluye login, resumen, inventario, ventas, compras, caja y reportes.
Una venta descuenta lotes en orden FIFO; una compra agrega stock y, cuando se
indica una caja, valida el saldo antes de registrar el egreso.

## Verificaciones

```bash
python -m compileall -q *.py
cd frontend && npm run build
```

No se versionan `venv/`, `tienda.db` ni claves.
