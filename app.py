from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sqlite3, hashlib, os, requests, json
from datetime import datetime, timedelta
import random

app = Flask(__name__)
app.secret_key = 'postventa_secret_2024'

DB = 'postventa.db'
OLLAMA_URL = 'http://localhost:11434/api/generate'
OLLAMA_MODEL = 'llama3'

# ── DB ──────────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT DEFAULT 'agent',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        status TEXT DEFAULT 'open',
        priority TEXT DEFAULT 'medium',
        category TEXT DEFAULT 'general',
        customer_name TEXT NOT NULL,
        customer_email TEXT NOT NULL,
        assigned_to INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        resolved_at TIMESTAMP,
        FOREIGN KEY (assigned_to) REFERENCES users(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS ticket_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket_id INTEGER NOT NULL,
        sender TEXT NOT NULL,
        sender_type TEXT NOT NULL,
        message TEXT NOT NULL,
        is_ai BOOLEAN DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (ticket_id) REFERENCES tickets(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_number TEXT UNIQUE NOT NULL,
        customer_name TEXT NOT NULL,
        customer_email TEXT NOT NULL,
        product TEXT NOT NULL,
        amount REAL NOT NULL,
        status TEXT DEFAULT 'processing',
        tracking_number TEXT,
        estimated_delivery TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS chat_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT UNIQUE NOT NULL,
        customer_name TEXT NOT NULL,
        customer_email TEXT NOT NULL,
        status TEXT DEFAULT 'active',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS chat_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        sender TEXT NOT NULL,
        message TEXT NOT NULL,
        is_ai BOOLEAN DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    # Admin por defecto
    pw = hashlib.sha256('admin123'.encode()).hexdigest()
    c.execute("INSERT OR IGNORE INTO users (username,email,password,role) VALUES (?,?,?,?)",
              ('admin','admin@postventa.com',pw,'admin'))
    pw2 = hashlib.sha256('agent123'.encode()).hexdigest()
    c.execute("INSERT OR IGNORE INTO users (username,email,password,role) VALUES (?,?,?,?)",
              ('agente1','agente1@postventa.com',pw2,'agent'))

    # Demo data
    demo_tickets = [
        ('Producto defectuoso','Recibí el artículo roto','open','high','reclamacion','Carlos López','carlos@email.com'),
        ('Retraso en entrega','Mi pedido lleva 15 días','in_progress','medium','seguimiento','María García','maria@email.com'),
        ('Cambio de talla','Necesito cambiar talla L por M','open','low','devolucion','Ana Martín','ana@email.com'),
        ('Factura incorrecta','El importe no coincide','resolved','high','facturacion','Pedro Ruiz','pedro@email.com'),
        ('No funciona el código','Cupón de descuento inválido','open','medium','general','Laura Sanz','laura@email.com'),
    ]
    for t in demo_tickets:
        c.execute("INSERT OR IGNORE INTO tickets (title,description,status,priority,category,customer_name,customer_email) VALUES (?,?,?,?,?,?,?)", t)

    demo_orders = [
        ('ORD-2024-001','Carlos López','carlos@email.com','Zapatillas Running Nike',89.99,'delivered','TRK123456','2024-01-10'),
        ('ORD-2024-002','María García','maria@email.com','Camiseta Polo Ralph Lauren',45.00,'shipped','TRK789012','2024-01-20'),
        ('ORD-2024-003','Ana Martín','ana@email.com','Vestido Zara',35.50,'processing',None,'2024-01-25'),
        ('ORD-2024-004','Pedro Ruiz','pedro@email.com','Pantalón Levi\'s 501',79.99,'delivered','TRK345678','2024-01-08'),
        ('ORD-2024-005','Laura Sanz','laura@email.com','Bolso de piel',120.00,'cancelled',None,None),
    ]
    for o in demo_orders:
        c.execute("INSERT OR IGNORE INTO orders (order_number,customer_name,customer_email,product,amount,status,tracking_number,estimated_delivery) VALUES (?,?,?,?,?,?,?,?)", o)

    conn.commit()
    conn.close()

# ── AUTH ─────────────────────────────────────────────────────────────────────

def hash_pw(pw): return hashlib.sha256(pw.encode()).hexdigest()
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

@app.route('/login', methods=['GET','POST'])
def login():
    error = None
    if request.method == 'POST':
        u = request.form['username']
        p = hash_pw(request.form['password'])
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username=? AND password=?", (u,p)).fetchone()
        conn.close()
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            return redirect(url_for('dashboard'))
        error = 'Credenciales incorrectas'
    return render_template('login.html', error=error)

@app.route('/register', methods=['GET','POST'])
def register():
    error = None
    if request.method == 'POST':
        u = request.form['username']
        e = request.form['email']
        p = hash_pw(request.form['password'])
        try:
            conn = get_db()
            conn.execute("INSERT INTO users (username,email,password) VALUES (?,?,?)", (u,e,p))
            conn.commit()
            conn.close()
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            error = 'Usuario o email ya registrado'
    return render_template('register.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ── DASHBOARD ────────────────────────────────────────────────────────────────

@app.route('/')
@login_required
def dashboard():
    conn = get_db()
    stats = {
        'tickets_open': conn.execute("SELECT COUNT(*) FROM tickets WHERE status='open'").fetchone()[0],
        'tickets_inprogress': conn.execute("SELECT COUNT(*) FROM tickets WHERE status='in_progress'").fetchone()[0],
        'tickets_resolved': conn.execute("SELECT COUNT(*) FROM tickets WHERE status='resolved'").fetchone()[0],
        'tickets_total': conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0],
        'orders_total': conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
        'orders_processing': conn.execute("SELECT COUNT(*) FROM orders WHERE status='processing'").fetchone()[0],
        'orders_shipped': conn.execute("SELECT COUNT(*) FROM orders WHERE status='shipped'").fetchone()[0],
    }
    recent_tickets = conn.execute(
        "SELECT t.*, u.username as agent FROM tickets t LEFT JOIN users u ON t.assigned_to=u.id ORDER BY t.created_at DESC LIMIT 5"
    ).fetchall()
    conn.close()
    return render_template('dashboard.html', stats=stats, recent_tickets=recent_tickets)

# ── TICKETS ──────────────────────────────────────────────────────────────────

@app.route('/tickets')
@login_required
def tickets():
    status = request.args.get('status','all')
    priority = request.args.get('priority','all')
    conn = get_db()
    q = "SELECT t.*, u.username as agent FROM tickets t LEFT JOIN users u ON t.assigned_to=u.id WHERE 1=1"
    params = []
    if status != 'all':
        q += " AND t.status=?"; params.append(status)
    if priority != 'all':
        q += " AND t.priority=?"; params.append(priority)
    q += " ORDER BY t.created_at DESC"
    ticket_list = conn.execute(q, params).fetchall()
    agents = conn.execute("SELECT * FROM users WHERE role IN ('agent','admin')").fetchall()
    conn.close()
    return render_template('tickets.html', tickets=ticket_list, agents=agents, status=status, priority=priority)

@app.route('/tickets/new', methods=['GET','POST'])
@login_required
def new_ticket():
    if request.method == 'POST':
        conn = get_db()
        conn.execute("""INSERT INTO tickets (title,description,status,priority,category,customer_name,customer_email,assigned_to)
                        VALUES (?,?,?,?,?,?,?,?)""",
                     (request.form['title'], request.form['description'],
                      request.form.get('status','open'), request.form.get('priority','medium'),
                      request.form.get('category','general'), request.form['customer_name'],
                      request.form['customer_email'],
                      request.form.get('assigned_to') or None))
        conn.commit()
        conn.close()
        return redirect(url_for('tickets'))
    conn = get_db()
    agents = conn.execute("SELECT * FROM users WHERE role IN ('agent','admin')").fetchall()
    conn.close()
    return render_template('new_ticket.html', agents=agents)

@app.route('/tickets/<int:tid>', methods=['GET','POST'])
@login_required
def ticket_detail(tid):
    conn = get_db()
    ticket = conn.execute("SELECT t.*, u.username as agent FROM tickets t LEFT JOIN users u ON t.assigned_to=u.id WHERE t.id=?", (tid,)).fetchone()
    messages = conn.execute("SELECT * FROM ticket_messages WHERE ticket_id=? ORDER BY created_at", (tid,)).fetchall()
    agents = conn.execute("SELECT * FROM users WHERE role IN ('agent','admin')").fetchall()
    conn.close()
    if not ticket:
        return redirect(url_for('tickets'))
    return render_template('ticket_detail.html', ticket=ticket, messages=messages, agents=agents)

@app.route('/tickets/<int:tid>/message', methods=['POST'])
@login_required
def ticket_message(tid):
    msg = request.form['message']
    conn = get_db()
    conn.execute("INSERT INTO ticket_messages (ticket_id,sender,sender_type,message) VALUES (?,?,?,?)",
                 (tid, session['username'], 'agent', msg))
    conn.execute("UPDATE tickets SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (tid,))
    conn.commit()
    conn.close()
    return redirect(url_for('ticket_detail', tid=tid))

@app.route('/tickets/<int:tid>/ai-suggest', methods=['POST'])
@login_required
def ai_suggest(tid):
    conn = get_db()
    ticket = conn.execute("SELECT * FROM tickets WHERE id=?", (tid,)).fetchone()
    conn.close()
    prompt = f"""Eres un agente de atención al cliente experto. 
Un cliente ha enviado el siguiente ticket de soporte:
Título: {ticket['title']}
Descripción: {ticket['description']}
Categoría: {ticket['category']}
Prioridad: {ticket['priority']}

Genera una respuesta profesional, empática y útil para el cliente en español. 
Máximo 3 párrafos cortos."""
    try:
        r = requests.post(OLLAMA_URL, json={'model': OLLAMA_MODEL, 'prompt': prompt, 'stream': False}, timeout=30)
        suggestion = r.json().get('response', 'No se pudo generar sugerencia.')
    except:
        suggestion = 'Servicio de IA no disponible. Asegúrate de tener Ollama corriendo con el modelo llama3.'
    return jsonify({'suggestion': suggestion})

@app.route('/tickets/<int:tid>/update', methods=['POST'])
@login_required
def update_ticket(tid):
    data = request.json
    conn = get_db()
    if 'status' in data:
        extra = ", resolved_at=CURRENT_TIMESTAMP" if data['status'] == 'resolved' else ""
        conn.execute(f"UPDATE tickets SET status=?, updated_at=CURRENT_TIMESTAMP{extra} WHERE id=?",
                     (data['status'], tid))
    if 'assigned_to' in data:
        conn.execute("UPDATE tickets SET assigned_to=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                     (data['assigned_to'] or None, tid))
    if 'priority' in data:
        conn.execute("UPDATE tickets SET priority=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                     (data['priority'], tid))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

# ── ORDERS ───────────────────────────────────────────────────────────────────

@app.route('/orders')
@login_required
def orders():
    status = request.args.get('status','all')
    conn = get_db()
    q = "SELECT * FROM orders WHERE 1=1"
    params = []
    if status != 'all':
        q += " AND status=?"; params.append(status)
    q += " ORDER BY created_at DESC"
    order_list = conn.execute(q, params).fetchall()
    conn.close()
    return render_template('orders.html', orders=order_list, status=status)

@app.route('/orders/<int:oid>', methods=['GET','POST'])
@login_required
def order_detail(oid):
    conn = get_db()
    order = conn.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    if request.method == 'POST':
        conn.execute("UPDATE orders SET status=?,tracking_number=?,estimated_delivery=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                     (request.form['status'], request.form.get('tracking_number',''),
                      request.form.get('estimated_delivery',''), oid))
        conn.commit()
        return redirect(url_for('orders'))
    conn.close()
    return render_template('order_detail.html', order=order)

@app.route('/orders/new', methods=['GET','POST'])
@login_required
def new_order():
    if request.method == 'POST':
        import random, string
        num = 'ORD-' + ''.join(random.choices(string.digits, k=8))
        conn = get_db()
        conn.execute("INSERT INTO orders (order_number,customer_name,customer_email,product,amount,status,tracking_number,estimated_delivery) VALUES (?,?,?,?,?,?,?,?)",
                     (num, request.form['customer_name'], request.form['customer_email'],
                      request.form['product'], float(request.form['amount']),
                      request.form.get('status','processing'),
                      request.form.get('tracking_number',''),
                      request.form.get('estimated_delivery','')))
        conn.commit()
        conn.close()
        return redirect(url_for('orders'))
    return render_template('new_order.html')

# ── CHAT ─────────────────────────────────────────────────────────────────────

@app.route('/chat')
@login_required
def chat():
    conn = get_db()
    sessions = conn.execute("SELECT * FROM chat_sessions ORDER BY created_at DESC").fetchall()
    conn.close()
    return render_template('chat.html', sessions=sessions)

@app.route('/chat/<session_id>')
@login_required
def chat_session(session_id):
    conn = get_db()
    chat_sess = conn.execute("SELECT * FROM chat_sessions WHERE session_id=?", (session_id,)).fetchone()
    msgs = conn.execute("SELECT * FROM chat_messages WHERE session_id=? ORDER BY created_at", (session_id,)).fetchall()
    conn.close()
    return render_template('chat_session.html', chat_session=chat_sess, messages=msgs)

@app.route('/chat/new', methods=['POST'])
@login_required
def create_chat_session():
    import uuid
    sid = str(uuid.uuid4())[:12]
    conn = get_db()
    conn.execute("INSERT INTO chat_sessions (session_id,customer_name,customer_email) VALUES (?,?,?)",
                 (sid, request.form['customer_name'], request.form['customer_email']))
    conn.commit()
    conn.close()
    return redirect(url_for('chat_session', session_id=sid))

@app.route('/chat/<session_id>/reply', methods=['POST'])
@login_required
def chat_reply(session_id):
    msg = request.form['message']
    conn = get_db()
    conn.execute("INSERT INTO chat_messages (session_id,sender,message) VALUES (?,?,?)",
                 (session_id, session['username'], msg))
    conn.commit()
    conn.close()
    return redirect(url_for('chat_session', session_id=session_id))

@app.route('/api/chat/ai', methods=['POST'])
@login_required
def chat_ai_reply():
    data = request.json
    history = data.get('history', [])
    customer = data.get('customer', 'Cliente')
    
    history_str = '\n'.join([f"{m['sender']}: {m['message']}" for m in history[-6:]])
    prompt = f"""Eres un agente de atención al cliente amable y profesional de una tienda online.
Responde siempre en español, de forma concisa y útil.
Historial de conversación:
{history_str}
Genera la siguiente respuesta del agente:"""
    try:
        r = requests.post(OLLAMA_URL, json={'model': OLLAMA_MODEL, 'prompt': prompt, 'stream': False}, timeout=30)
        reply = r.json().get('response', '').strip()
    except:
        reply = 'Servicio de IA no disponible temporalmente.'
    return jsonify({'reply': reply})

# ── AGENTS ───────────────────────────────────────────────────────────────────

@app.route('/agents')
@login_required
def agents():
    if session.get('role') != 'admin':
        return redirect(url_for('dashboard'))
    conn = get_db()
    agent_list = conn.execute("""
        SELECT u.*, 
               COUNT(DISTINCT CASE WHEN t.status='open' THEN t.id END) as open_tickets,
               COUNT(DISTINCT CASE WHEN t.status='resolved' THEN t.id END) as resolved_tickets
        FROM users u
        LEFT JOIN tickets t ON t.assigned_to=u.id
        GROUP BY u.id ORDER BY u.created_at DESC
    """).fetchall()
    conn.close()
    return render_template('agents.html', agents=agent_list)

@app.route('/agents/new', methods=['POST'])
@login_required
def new_agent():
    if session.get('role') != 'admin':
        return jsonify({'error': 'No autorizado'}), 403
    conn = get_db()
    try:
        conn.execute("INSERT INTO users (username,email,password,role) VALUES (?,?,?,?)",
                     (request.form['username'], request.form['email'],
                      hash_pw(request.form['password']), request.form.get('role','agent')))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()
    return redirect(url_for('agents'))

@app.route('/agents/<int:uid>/delete', methods=['POST'])
@login_required
def delete_agent(uid):
    if session.get('role') != 'admin':
        return jsonify({'error': 'No autorizado'}), 403
    conn = get_db()
    conn.execute("DELETE FROM users WHERE id=? AND id!=1", (uid,))
    conn.commit()
    conn.close()
    return redirect(url_for('agents'))

# ── REPORTS ──────────────────────────────────────────────────────────────────

@app.route('/reports')
@login_required
def reports():
    conn = get_db()
    # Tickets por estado
    by_status = conn.execute("SELECT status, COUNT(*) as count FROM tickets GROUP BY status").fetchall()
    by_priority = conn.execute("SELECT priority, COUNT(*) as count FROM tickets GROUP BY priority").fetchall()
    by_category = conn.execute("SELECT category, COUNT(*) as count FROM tickets GROUP BY category").fetchall()
    # Pedidos por estado
    orders_by_status = conn.execute("SELECT status, COUNT(*) as count FROM orders GROUP BY status").fetchall()
    # Agentes top
    top_agents = conn.execute("""
        SELECT u.username, COUNT(t.id) as total, 
               SUM(CASE WHEN t.status='resolved' THEN 1 ELSE 0 END) as resolved
        FROM users u LEFT JOIN tickets t ON t.assigned_to=u.id
        GROUP BY u.id ORDER BY total DESC LIMIT 5
    """).fetchall()
    # Tickets por día (últimos 7 días)
    daily = conn.execute("""
        SELECT DATE(created_at) as day, COUNT(*) as count 
        FROM tickets WHERE created_at >= DATE('now','-7 days')
        GROUP BY DATE(created_at) ORDER BY day
    """).fetchall()
    conn.close()
    return render_template('reports.html',
        by_status=by_status, by_priority=by_priority, by_category=by_category,
        orders_by_status=orders_by_status, top_agents=top_agents, daily=daily)

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)
