import os
import psycopg2
from psycopg2.extras import RealDictCursor
from urllib.parse import urlparse

def get_db_connection():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise Exception("❌ DATABASE_URL no configurada")
    
    result = urlparse(database_url)
    username = result.username
    password = result.password
    database = result.path[1:]
    hostname = result.hostname
    port = result.port or 5432

    conn = psycopg2.connect(
        host=hostname,
        database=database,
        user=username,
        password=password,
        port=port,
        cursor_factory=RealDictCursor
    )
    return conn

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Tabla de turnos con cliente_id
    cur.execute('''
        CREATE TABLE IF NOT EXISTS turnos (
            id SERIAL PRIMARY KEY,
            cliente_id TEXT NOT NULL,
            nombre TEXT NOT NULL,
            email TEXT NOT NULL,
            telefono TEXT,
            fecha DATE NOT NULL,
            hora TIME NOT NULL,
            motivo TEXT,
            estado TEXT DEFAULT 'pendiente',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Índice para mejorar rendimiento
    cur.execute('''
        CREATE INDEX IF NOT EXISTS idx_turnos_cliente ON turnos(cliente_id);
    ''')
    
    # Tabla de horarios por cliente
    cur.execute('''
        CREATE TABLE IF NOT EXISTS config_horarios (
            cliente_id TEXT NOT NULL,
            dia_semana INTEGER NOT NULL,
            hora_inicio TIME DEFAULT '09:00:00',
            hora_fin TIME DEFAULT '18:00:00',
            intervalo INTEGER DEFAULT 30,
            activo BOOLEAN DEFAULT TRUE,
            PRIMARY KEY (cliente_id, dia_semana)
        )
    ''')
    
    # Índice
    cur.execute('''
        CREATE INDEX IF NOT EXISTS idx_horarios_cliente ON config_horarios(cliente_id);
    ''')
    
    conn.commit()
    cur.close()
    conn.close()