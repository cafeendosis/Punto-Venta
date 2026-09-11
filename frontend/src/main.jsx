import { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const emptyProduct = { codigo_barras: '', nombre: '', precio_venta: '', categoria: '', stock_minimo: 0 }

function App() {
  const [token, setToken] = useState(localStorage.getItem('pos_token'))
  const [user, setUser] = useState(null)
  const [page, setPage] = useState('dashboard')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [summary, setSummary] = useState(null)
  const [products, setProducts] = useState([])
  const [cash, setCash] = useState(null)
  const [product, setProduct] = useState(emptyProduct)
  const [sale, setSale] = useState({ codigo_barras: '', cantidad: 1, caja_id: '', metodo_pago: 'efectivo', efectivo_recibido: '' })
  const [purchase, setPurchase] = useState({ codigo_barras: '', cantidad: 1, precio_compra: '', proveedor: '', caja_id: '' })
  const [opening, setOpening] = useState('')
  const [closing, setClosing] = useState('')
  const [login, setLogin] = useState({ usuario: '', password: '' })

  const request = async (path, options = {}) => {
    const response = await fetch(`${API}${path}`, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(options.headers || {}) }
    })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(data.detail || 'No se pudo completar la operación')
    return data
  }
  const refresh = async () => {
    const [items, report] = await Promise.all([request('/productos'), request('/reportes/resumen').catch(() => null)])
    setProducts(items); setSummary(report)
    if (token) setCash(await request('/cajas/actual').catch(() => null))
  }
  useEffect(() => { if (token) { request('/auth/me').then(setUser).catch(() => logout()); refresh().catch(e => setError(e.message)) } }, [token])
  const logout = () => { localStorage.removeItem('pos_token'); setToken(null); setUser(null) }
  const run = async (operation, success) => {
    setError(''); setMessage('')
    try { await operation(); setMessage(success); await refresh() } catch (e) { setError(e.message) }
  }
  const loginSubmit = e => { e.preventDefault(); run(async () => { const data = await request('/auth/login', { method: 'POST', body: JSON.stringify(login) }); localStorage.setItem('pos_token', data.access_token); setToken(data.access_token); setUser(data.usuario) }, 'Bienvenido') }

  if (!token) return <main className="login-shell"><form className="login-card" onSubmit={loginSubmit}><div className="logo">🛒</div><h1>Abarrotes POS</h1><p>Control de ventas e inventario</p><label>Usuario<input required value={login.usuario} onChange={e => setLogin({ ...login, usuario: e.target.value })} /></label><label>Contraseña<input required type="password" value={login.password} onChange={e => setLogin({ ...login, password: e.target.value })} /></label>{error && <div className="alert error">{error}</div>}<button>Iniciar sesión</button><small>Primer acceso: registra un usuario con POST /auth/register.</small></form></main>

  const cards = [
    ['Ventas del periodo', summary?.total_ventas ?? '—', 'accent'],
    ['Compras del periodo', summary?.total_compras ?? '—', 'orange'],
    ['Productos', summary?.productos ?? '—', 'blue'],
    ['Stock bajo', summary?.stock_bajo?.length ?? '—', 'red']
  ]
  const nav = [['dashboard', 'Resumen'], ['products', 'Inventario'], ['sales', 'Ventas'], ['purchases', 'Compras'], ['cash', 'Caja'], ['reports', 'Reportes']]
  return <div className="app-shell"><aside><div className="brand">🛒 <strong>ABARROTES</strong><span>POS</span></div><nav>{nav.map(([id, label]) => <button key={id} className={page === id ? 'active' : ''} onClick={() => setPage(id)}>{label}</button>)}</nav><div className="user-box"><b>{user?.usuario}</b><small>{user?.rol}</small><button onClick={logout}>Cerrar sesión</button></div></aside><section className="content"><header><div><span className="eyebrow">OPERACIÓN</span><h2>{nav.find(x => x[0] === page)?.[1]}</h2></div><span className={`cash-pill ${cash ? 'open' : ''}`}>{cash ? `Caja #${cash.id} · $${cash.saldo.toFixed(2)}` : 'Caja cerrada'}</span></header>{message && <div className="alert success">{message}</div>}{error && <div className="alert error">{error}</div>}{page === 'dashboard' && <Dashboard cards={cards} summary={summary} products={products} />}{page === 'products' && <Products products={products} product={product} setProduct={setProduct} run={run} request={request} />}{page === 'sales' && <Sales sale={sale} setSale={setSale} products={products} cash={cash} run={run} request={request} />}{page === 'purchases' && <Purchases purchase={purchase} setPurchase={setPurchase} products={products} cash={cash} run={run} request={request} />}{page === 'cash' && <Cash cash={cash} opening={opening} setOpening={setOpening} closing={closing} setClosing={setClosing} run={run} request={request} />}{page === 'reports' && <Reports summary={summary} products={products} />}</section></div>
}

function Dashboard({ cards, summary, products }) { return <><div className="cards">{cards.map(([label, value, color]) => <div className={`metric ${color}`} key={label}><span>{label}</span><strong>{typeof value === 'number' && label.includes('periodo') ? `$${value.toFixed(2)}` : value}</strong></div>)}</div><div className="grid two"><section className="panel"><h3>Alertas de inventario</h3>{summary?.stock_bajo?.length ? <table><tbody>{summary.stock_bajo.map(p => <tr key={p.codigo_barras}><td>{p.nombre}</td><td>{p.stock} / mínimo {p.minimo}</td></tr>)}</tbody></table> : <p className="muted">Todo el inventario está por encima del mínimo.</p>}</section><section className="panel"><h3>Productos recientes</h3><table><tbody>{products.slice(0, 5).map(p => <tr key={p.id}><td>{p.nombre}</td><td>${p.precio_venta.toFixed(2)}</td><td><span className="tag">{p.stock_total} uds.</span></td></tr>)}</tbody></table></section></div></> }

function Products({ products, product, setProduct, run, request }) { return <div className="grid two"><section className="panel"><h3>Nuevo producto</h3><form onSubmit={e => { e.preventDefault(); run(() => request('/productos/', { method: 'POST', body: JSON.stringify({ ...product, precio_venta: Number(product.precio_venta), stock_minimo: Number(product.stock_minimo) }) }), 'Producto guardado'); setProduct(emptyProduct) }}><label>Código de barras<input required value={product.codigo_barras} onChange={e => setProduct({ ...product, codigo_barras: e.target.value })} /></label><label>Nombre<input required value={product.nombre} onChange={e => setProduct({ ...product, nombre: e.target.value })} /></label><div className="form-row"><label>Precio venta<input required type="number" min="0.01" step="0.01" value={product.precio_venta} onChange={e => setProduct({ ...product, precio_venta: e.target.value })} /></label><label>Stock mínimo<input type="number" min="0" value={product.stock_minimo} onChange={e => setProduct({ ...product, stock_minimo: e.target.value })} /></label></div><label>Categoría<input value={product.categoria} onChange={e => setProduct({ ...product, categoria: e.target.value })} /></label><button>Guardar producto</button></form></section><section className="panel"><h3>Inventario <span className="count">{products.length}</span></h3><table><thead><tr><th>Producto</th><th>Código</th><th>Precio</th><th>Stock</th></tr></thead><tbody>{products.map(p => <tr key={p.id}><td><b>{p.nombre}</b><small>{p.categoria || 'Sin categoría'}</small></td><td>{p.codigo_barras}</td><td>${p.precio_venta.toFixed(2)}</td><td className={p.stock_total <= p.stock_minimo ? 'low' : ''}>{p.stock_total}</td></tr>)}</tbody></table></section></div> }

function Sales({ sale, setSale, products, cash, run, request }) { const selected = products.find(p => p.codigo_barras === sale.codigo_barras); const total = selected ? selected.precio_venta * Number(sale.cantidad || 0) : 0; return <section className="panel narrow"><h3>Registrar venta</h3><form onSubmit={e => { e.preventDefault(); run(() => request('/ventas/', { method: 'POST', body: JSON.stringify({ ...sale, caja_id: sale.caja_id ? Number(sale.caja_id) : null, cantidad: Number(sale.cantidad), efectivo_recibido: sale.efectivo_recibido ? Number(sale.efectivo_recibido) : null }) }), 'Venta registrada') }}><label>Producto<select required value={sale.codigo_barras} onChange={e => setSale({ ...sale, codigo_barras: e.target.value })}><option value="">Selecciona un producto</option>{products.map(p => <option key={p.id} value={p.codigo_barras}>{p.nombre} · {p.stock_total} uds.</option>)}</select></label><div className="form-row"><label>Cantidad<input type="number" min="1" required value={sale.cantidad} onChange={e => setSale({ ...sale, cantidad: e.target.value })} /></label><label>Método<select value={sale.metodo_pago} onChange={e => setSale({ ...sale, metodo_pago: e.target.value })}><option>efectivo</option><option>tarjeta</option><option>transferencia</option></select></label></div>{sale.metodo_pago === 'efectivo' && <label>Efectivo recibido<input type="number" min={total} step="0.01" value={sale.efectivo_recibido} onChange={e => setSale({ ...sale, efectivo_recibido: e.target.value })} /></label>}<label>Caja abierta<select value={sale.caja_id} onChange={e => setSale({ ...sale, caja_id: e.target.value })}><option value="">Sin caja (compatibilidad)</option>{cash && <option value={cash.id}>Caja #{cash.id}</option>}</select></label><div className="total">Total <strong>${total.toFixed(2)}</strong></div><button>Confirmar venta</button></form></section> }

function Purchases({ purchase, setPurchase, products, cash, run, request }) { return <section className="panel narrow"><h3>Registrar compra / entrada</h3><form onSubmit={e => { e.preventDefault(); run(() => request('/compras/', { method: 'POST', body: JSON.stringify({ ...purchase, cantidad: Number(purchase.cantidad), precio_compra: Number(purchase.precio_compra), caja_id: purchase.caja_id ? Number(purchase.caja_id) : null }) }), 'Compra registrada') }}><label>Producto<select required value={purchase.codigo_barras} onChange={e => setPurchase({ ...purchase, codigo_barras: e.target.value })}><option value="">Selecciona un producto</option>{products.map(p => <option key={p.id} value={p.codigo_barras}>{p.nombre}</option>)}</select></label><div className="form-row"><label>Cantidad<input type="number" min="1" required value={purchase.cantidad} onChange={e => setPurchase({ ...purchase, cantidad: e.target.value })} /></label><label>Precio compra<input type="number" min="0" step="0.01" required value={purchase.precio_compra} onChange={e => setPurchase({ ...purchase, precio_compra: e.target.value })} /></label></div><label>Proveedor<input value={purchase.proveedor} onChange={e => setPurchase({ ...purchase, proveedor: e.target.value })} /></label><label>Caja para egreso<select value={purchase.caja_id} onChange={e => setPurchase({ ...purchase, caja_id: e.target.value })}><option value="">No descontar de caja</option>{cash && <option value={cash.id}>Caja #{cash.id}</option>}</select></label><button>Guardar compra</button></form></section> }

function Cash({ cash, opening, setOpening, closing, setClosing, run, request }) { return <section className="panel narrow"><h3>Control de caja</h3>{cash ? <><div className="cash-balance"><span>Saldo actual</span><strong>${cash.saldo.toFixed(2)}</strong></div><form onSubmit={e => { e.preventDefault(); run(() => request(`/cajas/${cash.id}/cerrar`, { method: 'POST', body: JSON.stringify({ monto_cierre: Number(closing) }) }), 'Caja cerrada') }}><label>Conteo al cierre<input type="number" min="0" step="0.01" required value={closing} onChange={e => setClosing(e.target.value)} /></label><button className="danger">Cerrar caja</button></form></> : <form onSubmit={e => { e.preventDefault(); run(() => request('/cajas/abrir', { method: 'POST', body: JSON.stringify({ monto_apertura: Number(opening) }) }), 'Caja abierta'); setOpening('') }}><label>Fondo inicial<input type="number" min="0" step="0.01" required value={opening} onChange={e => setOpening(e.target.value)} /></label><button>Abrir caja</button></form>}</section> }

function Reports({ summary, products }) { return <><div className="cards">{[['Ventas', summary?.ventas], ['Compras', summary?.compras], ['Valor vendido', summary ? `$${summary.total_ventas.toFixed(2)}` : '—']].map(([l, v]) => <div className="metric accent" key={l}><span>{l}</span><strong>{v ?? '—'}</strong></div>)}</div><section className="panel"><h3>Reporte de inventario</h3><table><thead><tr><th>Producto</th><th>Categoría</th><th>Stock</th><th>Mínimo</th><th>Estado</th></tr></thead><tbody>{products.map(p => <tr key={p.id}><td>{p.nombre}</td><td>{p.categoria || '—'}</td><td>{p.stock_total}</td><td>{p.stock_minimo}</td><td><span className={`tag ${p.stock_total <= p.stock_minimo ? 'danger-tag' : ''}`}>{p.stock_total <= p.stock_minimo ? 'Reponer' : 'Correcto'}</span></td></tr>)}</tbody></table></section></> }

createRoot(document.getElementById('root')).render(<App />)
