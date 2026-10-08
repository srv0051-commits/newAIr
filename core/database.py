import sqlite3, time, os
from contextlib import contextmanager
from flask import g
from config import DB_PATH, DATA_DIR

SCHEMA = """
CREATE TABLE IF NOT EXISTS characters(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 name TEXT NOT NULL,
 personality TEXT DEFAULT '',
 description TEXT DEFAULT '',
 tags TEXT DEFAULT '',
 scenario TEXT DEFAULT '',
 greeting TEXT DEFAULT '',
 example_dialogue TEXT DEFAULT '',
 system_prompt TEXT DEFAULT '',
 creator_notes TEXT DEFAULT '',
 appearance TEXT DEFAULT '',
 background TEXT DEFAULT '',
 avatar_path TEXT DEFAULT '',
 visual_style TEXT DEFAULT '',
 negative_prompt TEXT DEFAULT '',
 preferred_lora TEXT DEFAULT '',
 reference_images TEXT DEFAULT '[]',
 initial_messages TEXT DEFAULT '[]',
 image_preset TEXT DEFAULT 'balanced',
 visual_prompt TEXT DEFAULT '',
 visual_negative_prompt TEXT DEFAULT '',
 visual_prompt_updated_at REAL DEFAULT 0,
 created_at REAL NOT NULL,
 updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS personas(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 name TEXT NOT NULL,
 description TEXT DEFAULT '',
 avatar_path TEXT DEFAULT '',
 pronouns TEXT DEFAULT '',
 age TEXT DEFAULT '',
 appearance TEXT DEFAULT '',
 personality TEXT DEFAULT '',
 speaking_style TEXT DEFAULT '',
 background TEXT DEFAULT '',
 details TEXT DEFAULT '',
 created_at REAL NOT NULL,
 updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS conversations(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 character_id INTEGER REFERENCES characters(id) ON DELETE CASCADE,
 persona_id INTEGER REFERENCES personas(id) ON DELETE SET NULL,
 mode TEXT NOT NULL DEFAULT 'character' CHECK(mode IN ('character','assistant')),
 title TEXT DEFAULT '',
 created_at REAL NOT NULL,
 updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS messages(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
 role TEXT NOT NULL CHECK(role IN ('user','assistant','system')),
 content TEXT NOT NULL,
 created_at REAL NOT NULL,
 edited INTEGER NOT NULL DEFAULT 0,
 summarized INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS conversation_memories(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
 summary TEXT NOT NULL,
 covers_up_to_message_id INTEGER NOT NULL,
 created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS character_memories(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
 fact TEXT NOT NULL,
 category TEXT DEFAULT 'general',
 importance INTEGER DEFAULT 1,
 created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS lorebook_entries(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 character_id INTEGER REFERENCES characters(id) ON DELETE CASCADE,
 title TEXT NOT NULL,
 keywords TEXT NOT NULL,
 content TEXT NOT NULL,
 enabled INTEGER NOT NULL DEFAULT 1,
 priority INTEGER NOT NULL DEFAULT 0,
 created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS image_generations(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 filename TEXT NOT NULL,
 model TEXT DEFAULT '',
 model_family TEXT DEFAULT '',
 prompt TEXT NOT NULL,
 negative_prompt TEXT DEFAULT '',
 width INTEGER NOT NULL,
 height INTEGER NOT NULL,
 steps INTEGER NOT NULL,
 guidance REAL NOT NULL,
 sampler TEXT DEFAULT '',
 seed INTEGER DEFAULT -1,
 quality TEXT DEFAULT 'balanced',
 hires_enabled INTEGER DEFAULT 0,
 hires_scale REAL DEFAULT 1.5,
 hires_denoise REAL DEFAULT 0.35,
 strength REAL DEFAULT NULL,
 loras TEXT DEFAULT '[]',
 character_id INTEGER REFERENCES characters(id) ON DELETE SET NULL,
 parent_id INTEGER REFERENCES image_generations(id) ON DELETE SET NULL,
 favorite INTEGER DEFAULT 0,
 generation_ms INTEGER DEFAULT 0,
 created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_image_generations_created ON image_generations(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_image_generations_character ON image_generations(character_id);
"""

def now(): return time.time()

def _connect():
    c=sqlite3.connect(DB_PATH)
    c.row_factory=sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA journal_mode=WAL")
    return c

@contextmanager
def db_cursor():
    conn=getattr(g,"_newair_db",None)
    if conn is None:
        conn=_connect(); g._newair_db=conn
    try:
        yield conn.cursor(); conn.commit()
    except Exception:
        conn.rollback(); raise

def _ensure(conn,table,col,definition):
    cols={r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if col not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {definition}")

def init_db():
    os.makedirs(DATA_DIR,exist_ok=True)
    conn=_connect()
    try:
        conn.executescript(SCHEMA)
        character_cols=[
            ("description","TEXT DEFAULT ''"),("tags","TEXT DEFAULT ''"),
            ("system_prompt","TEXT DEFAULT ''"),("creator_notes","TEXT DEFAULT ''"),
            ("appearance","TEXT DEFAULT ''"),("background","TEXT DEFAULT ''"),
            ("avatar_path","TEXT DEFAULT ''"),("visual_style","TEXT DEFAULT ''"),
            ("negative_prompt","TEXT DEFAULT ''"),("preferred_lora","TEXT DEFAULT ''"),
            ("reference_images","TEXT DEFAULT '[]'"),("initial_messages","TEXT DEFAULT '[]'"),("image_preset","TEXT DEFAULT 'balanced'"),
            ("visual_prompt","TEXT DEFAULT ''"),("visual_negative_prompt","TEXT DEFAULT ''"),("visual_prompt_updated_at","REAL DEFAULT 0"),
        ]
        for col,typ in character_cols: _ensure(conn,"characters",col,typ)
        persona_cols=[("avatar_path","TEXT DEFAULT ''"),("pronouns","TEXT DEFAULT ''"),("age","TEXT DEFAULT ''"),("appearance","TEXT DEFAULT ''"),("personality","TEXT DEFAULT ''"),("details","TEXT DEFAULT ''")]
        for col,typ in persona_cols: _ensure(conn,"personas",col,typ)
        for col,typ in [
            ("category","TEXT DEFAULT 'general'"),("importance","INTEGER DEFAULT 1")
        ]: _ensure(conn,"character_memories",col,typ)

        # Migrate image_generations created by older newAIr builds.
        # SCHEMA only affects newly-created databases, so every column used by
        # the metadata writer must also be added to existing databases.
        image_generation_cols = [
            ("model","TEXT DEFAULT ''"),
            ("model_family","TEXT DEFAULT ''"),
            ("prompt","TEXT NOT NULL DEFAULT ''"),
            ("negative_prompt","TEXT DEFAULT ''"),
            ("width","INTEGER NOT NULL DEFAULT 512"),
            ("height","INTEGER NOT NULL DEFAULT 512"),
            ("steps","INTEGER NOT NULL DEFAULT 24"),
            ("guidance","REAL NOT NULL DEFAULT 5.0"),
            ("sampler","TEXT DEFAULT ''"),
            ("seed","INTEGER DEFAULT -1"),
            ("quality","TEXT DEFAULT 'balanced'"),
            ("hires_enabled","INTEGER DEFAULT 0"),
            ("hires_scale","REAL DEFAULT 1.5"),
            ("hires_denoise","REAL DEFAULT 0.35"),
            ("strength","REAL DEFAULT NULL"),
            ("loras","TEXT DEFAULT '[]'"),
            ("character_id","INTEGER"),
            ("parent_id","INTEGER"),
            ("favorite","INTEGER DEFAULT 0"),
            ("generation_ms","INTEGER DEFAULT 0"),
            ("created_at","REAL NOT NULL DEFAULT 0"),
        ]
        for col,typ in image_generation_cols:
            _ensure(conn,"image_generations",col,typ)

        conn.execute("CREATE INDEX IF NOT EXISTS idx_image_generations_created ON image_generations(created_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_image_generations_character ON image_generations(character_id)")
        if not conn.execute("SELECT id FROM characters WHERE id=0").fetchone():
            t=now(); conn.execute("INSERT INTO characters(id,name,created_at,updated_at) VALUES(0,'__ASSISTANT_MODE__',?,?)",(t,t))
        conn.commit()
    finally:
        conn.close()
