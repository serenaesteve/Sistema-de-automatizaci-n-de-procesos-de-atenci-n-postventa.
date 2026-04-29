# PostVenta Pro — Sistema de Automatización de Atención Postventa

## Stack
- **Backend**: Python Flask + SQLite
- **IA**: Ollama / LLaMA 3 (local, sin coste)
- **Frontend**: HTML/CSS/JS con diseño dark editorial

## Módulos
- ✅ Dashboard con estadísticas en tiempo real
- ✅ Gestión de tickets (CRUD, filtros, prioridades)
- ✅ Seguimiento de pedidos
- ✅ Chat con IA (LLaMA 3)
- ✅ Panel de agentes (solo admin)
- ✅ Reportes con gráficas (Chart.js)
- ✅ Login / Registro

## Instalación

```bash
# 1. Instalar dependencias
pip install -r requirements.txt

# 2. Tener Ollama corriendo con LLaMA 3
ollama serve
ollama pull llama3

# 3. Ejecutar la app
python app.py
```

## Acceso
- URL: http://localhost:5000
- Admin: `admin` / `admin123`
- Agente demo: `agente1` / `agent123`

## Estructura
```
postventa/
├── app.py              # Flask app principal
├── requirements.txt
├── postventa.db        # Se crea automáticamente
└── templates/
    ├── base.html
    ├── login.html
    ├── register.html
    ├── dashboard.html
    ├── tickets.html
    ├── ticket_detail.html
    ├── new_ticket.html
    ├── orders.html
    ├── order_detail.html
    ├── new_order.html
    ├── chat.html
    ├── chat_session.html
    ├── agents.html
    └── reports.html
```

## Configuración de IA
En `app.py` líneas 11-12:
```python
OLLAMA_URL = 'http://localhost:11434/api/generate'
OLLAMA_MODEL = 'llama3'  # Cambia por el modelo que tengas
```
