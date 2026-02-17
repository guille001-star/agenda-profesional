import os
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional
import database

app = FastAPI(title="AgendaProfesional")
templates = Jinja2Templates(directory="templates")

# Inicializar DB
database.init_db()

class TurnoCreate(BaseModel):
    nombre: str
    email: str
    telefono: Optional[str] = None
    fecha: str
    hora: str
    motivo: Optional[str] = None

def normalize_cliente_id(nombre: str) -> str:
    """Convierte 'Abogado Martínez' → 'abogado-martinez'"""
    import re
    nombre = nombre.lower()
    nombre = re.sub(r'[^\w\s-]', '', nombre)
    nombre = re.sub(r'[-\s]+', '-', nombre).strip('-')
    return nombre or "default"

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/horarios/{fecha}")
async def get_horarios_disponibles(fecha: str, request: Request):
    try:
        cliente_nombre = request.query_params.get("cliente", "Estudio Profesional")
        cliente_id = normalize_cliente_id(cliente_nombre)
        
        fecha_obj = datetime.strptime(fecha, '%Y-%m-%d')
        dia_semana = fecha_obj.weekday() + 1
        
        conn = database.get_db_connection()
        cur = conn.cursor()
        
        # Verificar o crear configuración por defecto
        cur.execute('SELECT 1 FROM config_horarios WHERE cliente_id = %s AND dia_semana = %s', (cliente_id, dia_semana))
        if not cur.fetchone():
            # Crear horarios por defecto (lunes-viernes 9-18, sábados 10-14)
            hora_inicio = '09:00:00' if dia_semana <= 5 else '10:00:00'
            hora_fin = '18:00:00' if dia_semana <= 5 else '14:00:00'
            activo = True if dia_semana <= 5 else False
            cur.execute('''
                INSERT INTO config_horarios (cliente_id, dia_semana, hora_inicio, hora_fin, intervalo, activo)
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (cliente_id, dia_semana, hora_inicio, hora_fin, 30, activo))
            conn.commit()
        
        cur.execute('SELECT * FROM config_horarios WHERE cliente_id = %s AND dia_semana = %s', (cliente_id, dia_semana))
        config = cur.fetchone()
        
        if not config or not config['activo']:
            cur.close()
            conn.close()
            return {"horarios": []}
        
        # Horarios ocupados
        cur.execute('SELECT hora FROM turnos WHERE cliente_id = %s AND fecha = %s AND estado != %s', 
                   (cliente_id, fecha, 'cancelado'))
        ocupados = {row['hora'].strftime('%H:%M') for row in cur.fetchall()}
        
        # Generar horarios
        inicio = datetime.strptime(config['hora_inicio'].strftime('%H:%M'), '%H:%M')
        fin = datetime.strptime(config['hora_fin'].strftime('%H:%M'), '%H:%M')
        intervalo = config['intervalo']
        
        horarios = []
        current = inicio
        while current < fin:
            h_str = current.strftime('%H:%M')
            if h_str not in ocupados:
                horarios.append(h_str)
            current += timedelta(minutes=intervalo)
        
        cur.close()
        conn.close()
        return {"horarios": horarios}
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Fecha inválida")

@app.post("/api/turnos")
async def crear_turno(turno: TurnoCreate, request: Request):
    try:
        cliente_nombre = request.query_params.get("cliente", "Estudio Profesional")
        cliente_id = normalize_cliente_id(cliente_nombre)
        
        fecha_turno = datetime.strptime(turno.fecha, '%Y-%m-%d').date()
        hoy = datetime.now().date()
        if fecha_turno < hoy:
            return JSONResponse({"success": False, "error": "No se aceptan fechas pasadas"})
        
        conn = database.get_db_connection()
        cur = conn.cursor()
        
        cur.execute('SELECT 1 FROM turnos WHERE cliente_id = %s AND fecha = %s AND hora = %s AND estado != %s', 
                   (cliente_id, turno.fecha, turno.hora, 'cancelado'))
        if cur.fetchone():
            return JSONResponse({"success": False, "error": "Horario ya reservado"})
        
        cur.execute('''
            INSERT INTO turnos (cliente_id, nombre, email, telefono, fecha, hora, motivo)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', (cliente_id, turno.nombre, turno.email, turno.telefono, turno.fecha, turno.hora, turno.motivo))
        
        conn.commit()
        cur.close()
        conn.close()
        return JSONResponse({"success": True})
        
    except Exception as e:
        return JSONResponse({"success": False, "error": "Error al agendar"})

# === RUTAS ADMIN ===
@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request):
    return templates.TemplateResponse("admin_panel.html", {"request": request})

@app.get("/api/admin/estadisticas")
async def get_estadisticas(request: Request):
    cliente_nombre = request.query_params.get("cliente", "Estudio Profesional")
    cliente_id = normalize_cliente_id(cliente_nombre)
    
    conn = database.get_db_connection()
    cur = conn.cursor()
    
    cur.execute('SELECT COUNT(*) FROM turnos WHERE cliente_id = %s', (cliente_id,))
    total = cur.fetchone()['count']
    
    cur.execute('SELECT COUNT(*) FROM turnos WHERE cliente_id = %s AND estado = %s', (cliente_id, 'pendiente'))
    confirmados = cur.fetchone()['count']
    
    hoy = datetime.now().strftime('%Y-%m-%d')
    cur.execute('SELECT COUNT(*) FROM turnos WHERE cliente_id = %s AND fecha = %s AND estado != %s', 
               (cliente_id, hoy, 'cancelado'))
    hoy_count = cur.fetchone()['count']
    
    cur.execute('SELECT COUNT(*) FROM turnos WHERE cliente_id = %s AND estado = %s', (cliente_id, 'cancelado'))
    cancelados = cur.fetchone()['count']
    
    cur.close()
    conn.close()
    return {
        "total": total,
        "confirmados": confirmados,
        "hoy": hoy_count,
        "cancelados": cancelados
    }

@app.get("/api/admin/turnos")
async def get_turnos(request: Request):
    cliente_nombre = request.query_params.get("cliente", "Estudio Profesional")
    cliente_id = normalize_cliente_id(cliente_nombre)
    
    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM turnos WHERE cliente_id = %s ORDER BY created_at DESC', (cliente_id,))
    turnos = cur.fetchall()
    cur.close()
    conn.close()
    return {"turnos": [dict(t) for t in turnos]}

@app.get("/api/admin/horarios")
async def get_horarios_admin(request: Request):
    cliente_nombre = request.query_params.get("cliente", "Estudio Profesional")
    cliente_id = normalize_cliente_id(cliente_nombre)
    
    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM config_horarios WHERE cliente_id = %s ORDER BY dia_semana', (cliente_id,))
    horarios = cur.fetchall()
    cur.close()
    conn.close()
    return {"horarios": [dict(h) for h in horarios]}

@app.put("/api/admin/horarios/{dia}")
async def update_horario(dia: int, request: Request):
    if not (1 <= dia <= 7):
        raise HTTPException(status_code=400, detail="Día inválido")
    
    body = await request.json()
    cliente_nombre = request.query_params.get("cliente", "Estudio Profesional")
    cliente_id = normalize_cliente_id(cliente_nombre)
    
    conn = database.get_db_connection()
    cur = conn.cursor()
    
    cur.execute('''
        INSERT INTO config_horarios (cliente_id, dia_semana, hora_inicio, hora_fin, intervalo, activo)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (cliente_id, dia_semana) 
        DO UPDATE SET 
            hora_inicio = EXCLUDED.hora_inicio,
            hora_fin = EXCLUDED.hora_fin,
            intervalo = EXCLUDED.intervalo,
            activo = EXCLUDED.activo
    ''', (
        cliente_id,
        dia,
        body.get("hora_inicio", "09:00:00"),
        body.get("hora_fin", "18:00:00"),
        int(body.get("intervalo", 30)),
        bool(body.get("activo", False))
    ))
    
    conn.commit()
    cur.close()
    conn.close()
    return JSONResponse({"success": True})

@app.post("/api/admin/turnos/{id}/cancelar")
async def cancelar_turno(id: int, request: Request):
    cliente_nombre = request.query_params.get("cliente", "Estudio Profesional")
    cliente_id = normalize_cliente_id(cliente_nombre)
    
    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute('UPDATE turnos SET estado = %s WHERE id = %s AND cliente_id = %s', ('cancelado', id, cliente_id))
    conn.commit()
    cur.close()
    conn.close()
    return {"success": True}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=port)