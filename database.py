import sqlite3
import os
from typing import Optional, List, Dict, Any

DB_FILE = os.path.join(os.path.dirname(__file__), "app.db")

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        
        # 1. Users table (with google_uid support)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL DEFAULT '',
                google_uid TEXT UNIQUE,
                email TEXT,
                avatar TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Add google_uid column if it doesn't exist (migration)
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN google_uid TEXT UNIQUE")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN email TEXT")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN avatar TEXT")
        except Exception:
            pass
        
        # 2. Conversations table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        
        # 3. Messages table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            )
        """)
        
        conn.commit()

# --- User Queries ---

def create_user(name: str, username: str, password_hash: str) -> Optional[Dict[str, Any]]:
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (name, username, password_hash) VALUES (?, ?, ?)",
                (name, username.lower().strip(), password_hash)
            )
            user_id = cursor.lastrowid
            conn.commit()
            return {"id": user_id, "name": name, "username": username.lower().strip()}
    except sqlite3.IntegrityError:
        return None

def create_or_get_google_user(google_uid: str, name: str, email: str, avatar: str = "") -> Optional[Dict[str, Any]]:
    """Create or find user by Google UID."""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Check if user already exists by google_uid
        cursor.execute("SELECT id, name, username, email, avatar FROM users WHERE google_uid = ?", (google_uid,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        
        # Check if user exists by email
        cursor.execute("SELECT id, name, username, email, avatar FROM users WHERE email = ?", (email,))
        row = cursor.fetchone()
        if row:
            # Link Google UID to existing account
            cursor.execute("UPDATE users SET google_uid = ?, avatar = ? WHERE email = ?", (google_uid, avatar, email))
            conn.commit()
            return dict(row)
        
        # Create new Google user
        # Generate a unique username from email
        base_username = email.split("@")[0].lower().replace(".", "_")[:20]
        username = base_username
        counter = 1
        while True:
            cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
            if not cursor.fetchone():
                break
            username = f"{base_username}{counter}"
            counter += 1
        
        try:
            cursor.execute(
                "INSERT INTO users (name, username, password_hash, google_uid, email, avatar) VALUES (?, ?, '', ?, ?, ?)",
                (name, username, google_uid, email, avatar)
            )
            user_id = cursor.lastrowid
            conn.commit()
            return {"id": user_id, "name": name, "username": username, "email": email, "avatar": avatar}
        except sqlite3.IntegrityError:
            return None

def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username.lower().strip(),))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, username, email, avatar, created_at FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

# --- Conversation Queries ---

def create_conversation(conv_id: str, user_id: int, title: str) -> Dict[str, Any]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO conversations (id, user_id, title) VALUES (?, ?, ?)",
            (conv_id, user_id, title)
        )
        conn.commit()
        return {"id": conv_id, "user_id": user_id, "title": title}

def get_user_conversations(user_id: int) -> List[Dict[str, Any]]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, title, created_at FROM conversations WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,)
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def delete_conversation(conv_id: str, user_id: int) -> bool:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM conversations WHERE id = ? AND user_id = ?", (conv_id, user_id))
        conn.commit()
        return cursor.rowcount > 0

def update_conversation_title(conv_id: str, user_id: int, title: str):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE conversations SET title = ? WHERE id = ? AND user_id = ?",
            (title, conv_id, user_id)
        )
        conn.commit()

# --- Message Queries ---

def add_message(conv_id: str, role: str, content: str):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)",
            (conv_id, role, content)
        )
        conn.commit()

def get_conversation_messages(conv_id: str, user_id: int) -> List[Dict[str, Any]]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM conversations WHERE id = ? AND user_id = ?", (conv_id, user_id))
        if not cursor.fetchone():
            return []
        
        cursor.execute(
            "SELECT role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY id ASC",
            (conv_id,)
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

# Initialize DB when imported
init_db()
