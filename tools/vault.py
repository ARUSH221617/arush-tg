import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from config import settings

DB_PATH = settings.VAULT_DATA_DIR / "db" / "vault.sqlite"

class ProjectVault:
    """
    Project Knowledge Vault and Life Manager Database (SQLite).
    Stores projects, screenshots, ideas, receipts, financials, habits, and health logs.
    """

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._get_conn() as conn:
            cursor = conn.cursor()

            # 1. Projects table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                slug TEXT UNIQUE NOT NULL,
                client TEXT,
                platform TEXT DEFAULT 'direct',
                status TEXT DEFAULT 'lead',
                budget TEXT,
                github_repo TEXT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

            # 2. Vault Artifacts (Screenshots, Ideas, Notes, Audio Memos, Files)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS vault_artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                type TEXT NOT NULL,
                title TEXT,
                content TEXT,
                file_path TEXT,
                tags TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
            """)

            # 3. Financial Ledger (Invoices, Receipts, Card-to-Card)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS financial_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                amount REAL NOT NULL,
                currency TEXT DEFAULT 'Toman',
                category TEXT DEFAULT 'income',
                tracking_code TEXT,
                date TEXT,
                description TEXT,
                receipt_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects(id)
            )
            """)

            # 4. Habits & Health Logs
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS health_and_habits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                value TEXT NOT NULL,
                notes TEXT,
                logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            conn.commit()

    # --- Project Methods ---
    def create_or_get_project(self, name: str, client: str = "", platform: str = "direct") -> Dict[str, Any]:
        slug = "".join(c if c.isalnum() else "_" for c in name.lower().strip())
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM projects WHERE slug = ?", (slug,))
            row = cursor.fetchone()
            if row:
                return dict(row)

            # Create project directory
            proj_dir = settings.VAULT_DATA_DIR / "projects" / slug
            proj_dir.mkdir(parents=True, exist_ok=True)

            cursor.execute(
                "INSERT INTO projects (name, slug, client, platform) VALUES (?, ?, ?, ?)",
                (name, slug, client, platform)
            )
            conn.commit()
            cursor.execute("SELECT * FROM projects WHERE id = ?", (cursor.lastrowid,))
            return dict(cursor.fetchone())

    def list_projects(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            if status:
                cursor.execute("SELECT * FROM projects WHERE status = ? ORDER BY id DESC", (status,))
            else:
                cursor.execute("SELECT * FROM projects ORDER BY id DESC")
            return [dict(row) for row in cursor.fetchall()]

    # --- Artifact & Knowledge Methods ---
    def save_artifact(
        self,
        artifact_type: str,
        title: str,
        content: str,
        project_slug: Optional[str] = None,
        file_path: Optional[str] = None,
        tags: Optional[str] = None
    ) -> Dict[str, Any]:
        project_id = None
        if project_slug:
            proj = self.create_or_get_project(project_slug)
            project_id = proj["id"]

        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO vault_artifacts (project_id, type, title, content, file_path, tags)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (project_id, artifact_type, title, content, file_path, tags or ""))
            conn.commit()
            cursor.execute("SELECT * FROM vault_artifacts WHERE id = ?", (cursor.lastrowid,))
            return dict(cursor.fetchone())

    def search_vault(self, query: str, artifact_type: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            like_query = f"%{query}%"
            if artifact_type:
                cursor.execute("""
                SELECT a.*, p.name as project_name 
                FROM vault_artifacts a
                LEFT JOIN projects p ON a.project_id = p.id
                WHERE a.type = ? AND (a.title LIKE ? OR a.content LIKE ? OR a.tags LIKE ?)
                ORDER BY a.id DESC LIMIT ?
                """, (artifact_type, like_query, like_query, like_query, limit))
            else:
                cursor.execute("""
                SELECT a.*, p.name as project_name 
                FROM vault_artifacts a
                LEFT JOIN projects p ON a.project_id = p.id
                WHERE (a.title LIKE ? OR a.content LIKE ? OR a.tags LIKE ?)
                ORDER BY a.id DESC LIMIT ?
                """, (like_query, like_query, like_query, limit))
            return [dict(row) for row in cursor.fetchall()]

    # --- Financial Ledger Methods ---
    def record_transaction(
        self,
        amount: float,
        currency: str = "Toman",
        category: str = "income",
        tracking_code: Optional[str] = None,
        description: Optional[str] = None,
        receipt_path: Optional[str] = None,
        project_slug: Optional[str] = None
    ) -> Dict[str, Any]:
        project_id = None
        if project_slug:
            proj = self.create_or_get_project(project_slug)
            project_id = proj["id"]

        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO financial_ledger (project_id, amount, currency, category, tracking_code, description, receipt_path)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (project_id, amount, currency, category, tracking_code, description, receipt_path))
            conn.commit()
            cursor.execute("SELECT * FROM financial_ledger WHERE id = ?", (cursor.lastrowid,))
            return dict(cursor.fetchone())

    # --- Health & Habits Methods ---
    def log_health_or_habit(self, log_type: str, metric_name: str, value: str, notes: str = "") -> Dict[str, Any]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO health_and_habits (type, metric_name, value, notes)
            VALUES (?, ?, ?, ?)
            """, (log_type, metric_name, value, notes))
            conn.commit()
            cursor.execute("SELECT * FROM health_and_habits WHERE id = ?", (cursor.lastrowid,))
            return dict(cursor.fetchone())

vault = ProjectVault()
