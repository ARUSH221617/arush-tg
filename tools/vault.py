import sqlite3
import json
import math
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
from config import settings
from core.router_client import compute_local_embedding

DB_PATH = settings.VAULT_DATA_DIR / "db" / "vault.sqlite"


def _cosine_similarity(v1: List[float], v2: List[float]) -> float:
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    n1 = math.sqrt(sum(a * a for a in v1))
    n2 = math.sqrt(sum(b * b for b in v2))
    if n1 == 0.0 or n2 == 0.0:
        return 0.0
    return dot / (n1 * n2)


def slugify_project(name: str) -> str:
    clean = re.sub(r"[^\w\u0600-\u06FF]+", "_", name.lower().strip()).strip("_")
    return clean or "default_project"


class ProjectVault:
    """
    Project Knowledge Vault and Life Manager Database (SQLite).
    Implements:
    - Phase 2.1: Hierarchical Project Workspaces (context.md, specs.json, assets/)
    - Phase 2.2: Financial Ledger with Tracking Code Deduplication & Summaries
    - Phase 2.3: Voice Idea Incubator Storage
    - Phase 2.4: Semantic Vector Memory (Cosine Similarity + Embeddings)
    - Phase 3: Freelance Leads Storage
    - Phase 6: Medical Lab Results & Bio-Logging
    """

    def __init__(self, db_path: Path = DB_PATH, data_dir: Optional[Path] = None):
        self.db_path = db_path
        self.data_dir = data_dir or settings.VAULT_DATA_DIR
        self._active_project_slug: Optional[str] = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "projects").mkdir(parents=True, exist_ok=True)
        with self._get_conn() as conn:
            cursor = conn.cursor()

            # 1. Projects table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                slug TEXT UNIQUE NOT NULL,
                client TEXT DEFAULT '',
                platform TEXT DEFAULT 'direct',
                status TEXT DEFAULT 'in_progress',
                budget TEXT DEFAULT '',
                deadline TEXT DEFAULT '',
                github_repo TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                is_active INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

            # Ensure columns exist on upgraded DBs
            existing_proj_cols = {
                row["name"] for row in cursor.execute("PRAGMA table_info(projects)").fetchall()
            }
            if "deadline" not in existing_proj_cols:
                cursor.execute("ALTER TABLE projects ADD COLUMN deadline TEXT DEFAULT ''")
            if "is_active" not in existing_proj_cols:
                cursor.execute("ALTER TABLE projects ADD COLUMN is_active INTEGER DEFAULT 0")

            # 2. Vault Artifacts (Screenshots, Ideas, Notes, Audio Memos, Files)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS vault_artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                type TEXT NOT NULL,
                title TEXT,
                content TEXT,
                metadata_json TEXT DEFAULT '{}',
                file_path TEXT,
                tags TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
            """)
            existing_art_cols = {
                row["name"] for row in cursor.execute("PRAGMA table_info(vault_artifacts)").fetchall()
            }
            if "metadata_json" not in existing_art_cols:
                cursor.execute("ALTER TABLE vault_artifacts ADD COLUMN metadata_json TEXT DEFAULT '{}'")

            # 2.4 Semantic Vector Embeddings table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS vault_embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                artifact_id INTEGER UNIQUE NOT NULL,
                model TEXT NOT NULL,
                vector_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (artifact_id) REFERENCES vault_artifacts(id) ON DELETE CASCADE
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
                sender_card TEXT DEFAULT '',
                receiver_card TEXT DEFAULT '',
                bank_name TEXT DEFAULT '',
                transfer_type TEXT DEFAULT '',
                date TEXT DEFAULT '',
                description TEXT DEFAULT '',
                receipt_path TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects(id)
            )
            """)
            existing_fin_cols = {
                row["name"] for row in cursor.execute("PRAGMA table_info(financial_ledger)").fetchall()
            }
            for col in ("sender_card", "receiver_card", "bank_name", "transfer_type"):
                if col not in existing_fin_cols:
                    cursor.execute(f"ALTER TABLE financial_ledger ADD COLUMN {col} TEXT DEFAULT ''")

            # 4. Habits & Health Logs
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS health_and_habits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                value TEXT NOT NULL,
                unit TEXT DEFAULT '',
                is_completed INTEGER DEFAULT 1,
                notes TEXT DEFAULT '',
                logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            existing_hh_cols = {
                row["name"] for row in cursor.execute("PRAGMA table_info(health_and_habits)").fetchall()
            }
            if "unit" not in existing_hh_cols:
                cursor.execute("ALTER TABLE health_and_habits ADD COLUMN unit TEXT DEFAULT ''")
            if "is_completed" not in existing_hh_cols:
                cursor.execute("ALTER TABLE health_and_habits ADD COLUMN is_completed INTEGER DEFAULT 1")

            # 5. Medical Lab Results (Phase 6.1)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS medical_lab_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_category TEXT NOT NULL,
                biomarker TEXT NOT NULL,
                value REAL NOT NULL,
                unit TEXT DEFAULT '',
                reference_min REAL,
                reference_max REAL,
                flag TEXT DEFAULT 'NORMAL',
                lab_date TEXT DEFAULT '',
                source_file TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

            # 6. Freelance Leads (Phase 3)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS freelance_leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                external_id TEXT UNIQUE NOT NULL,
                platform TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                category TEXT DEFAULT '',
                budget_min REAL DEFAULT 0,
                budget_max REAL DEFAULT 0,
                currency TEXT DEFAULT 'Toman',
                employer_name TEXT DEFAULT '',
                employer_rating REAL DEFAULT 0.0,
                url TEXT DEFAULT '',
                match_score INTEGER DEFAULT 0,
                suggested_bid TEXT DEFAULT '',
                suggested_timeline TEXT DEFAULT '',
                proposal_draft TEXT DEFAULT '',
                notified INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            conn.commit()

    # ==========================================================
    # Phase 2.1: Hierarchical Project Vault & Workspaces
    # ==========================================================
    def _ensure_project_workspace(
        self,
        slug: str,
        name: str,
        client: str = "",
        platform: str = "direct",
        specs: Optional[Dict[str, Any]] = None
    ) -> Path:
        """
        Ensures `data/projects/{slug}/` exists with:
        - `context.md`
        - `specs.json`
        - `assets/`
        """
        proj_dir = self.data_dir / "projects" / slug
        assets_dir = proj_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)

        context_file = proj_dir / "context.md"
        if not context_file.exists():
            context_file.write_text(
                f"# Project: {name} (`{slug}`)\n\n"
                f"- **Client:** {client or 'N/A'}\n"
                f"- **Platform:** {platform}\n"
                f"- **Created:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n\n"
                f"## Overview & Requirements\n"
                f"Project workspace initialized.\n\n"
                f"## Activity Log\n",
                encoding="utf-8"
            )

        specs_file = proj_dir / "specs.json"
        if not specs_file.exists():
            default_specs = {
                "name": name,
                "slug": slug,
                "client": client,
                "platform": platform,
                "tech_stack": [],
                "deliverables": [],
                "milestones": [],
                "updated_at": datetime.utcnow().isoformat()
            }
            if specs:
                default_specs.update(specs)
            specs_file.write_text(json.dumps(default_specs, ensure_ascii=False, indent=2), encoding="utf-8")
        elif specs:
            try:
                current = json.loads(specs_file.read_text(encoding="utf-8"))
            except Exception:
                current = {}
            current.update(specs)
            current["updated_at"] = datetime.utcnow().isoformat()
            specs_file.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")

        return proj_dir

    def create_or_get_project(
        self,
        name: str,
        client: str = "",
        platform: str = "direct",
        budget: str = "",
        deadline: str = "",
        specs: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        slug = slugify_project(name)
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM projects WHERE slug = ?", (slug,))
            row = cursor.fetchone()
            if row:
                proj_dict = dict(row)
                self._ensure_project_workspace(
                    slug=slug,
                    name=proj_dict["name"],
                    client=client or proj_dict.get("client", ""),
                    platform=platform or proj_dict.get("platform", "direct"),
                    specs=specs
                )
                return proj_dict

            self._ensure_project_workspace(slug=slug, name=name, client=client, platform=platform, specs=specs)

            cursor.execute(
                """
                INSERT INTO projects (name, slug, client, platform, status, budget, deadline)
                VALUES (?, ?, ?, ?, 'in_progress', ?, ?)
                """,
                (name, slug, client, platform, budget, deadline)
            )
            conn.commit()
            cursor.execute("SELECT * FROM projects WHERE id = ?", (cursor.lastrowid,))
            return dict(cursor.fetchone())

    def switch_active_project(self, name_or_slug: str) -> Dict[str, Any]:
        """Creates or selects a project and marks it as the active workspace."""
        proj = self.create_or_get_project(name_or_slug)
        slug = proj["slug"]
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE projects SET is_active = 0")
            cursor.execute("UPDATE projects SET is_active = 1 WHERE slug = ?", (slug,))
            conn.commit()
            cursor.execute("SELECT * FROM projects WHERE slug = ?", (slug,))
            updated = dict(cursor.fetchone())
        self._active_project_slug = slug
        return updated

    def get_active_project(self) -> Optional[Dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM projects WHERE is_active = 1 LIMIT 1")
            row = cursor.fetchone()
            if row:
                self._active_project_slug = row["slug"]
                return dict(row)
        return None

    def get_project_summary(self, name_or_slug: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Returns comprehensive project details, workspace paths, artifact counts, and financial totals."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            if name_or_slug:
                slug = slugify_project(name_or_slug)
                cursor.execute("SELECT * FROM projects WHERE slug = ? OR LOWER(name) = LOWER(?)", (slug, name_or_slug))
            else:
                cursor.execute("SELECT * FROM projects WHERE is_active = 1 LIMIT 1")
            row = cursor.fetchone()
            if not row:
                return None

            proj = dict(row)
            pid = proj["id"]
            slug = proj["slug"]

            cursor.execute("SELECT type, COUNT(*) as cnt FROM vault_artifacts WHERE project_id = ? GROUP BY type", (pid,))
            artifact_counts = {r["type"]: r["cnt"] for r in cursor.fetchall()}

            cursor.execute(
                "SELECT category, SUM(amount) as total FROM financial_ledger WHERE project_id = ? GROUP BY category",
                (pid,)
            )
            fin_totals = {r["category"]: float(r["total"] or 0.0) for r in cursor.fetchall()}

            proj_dir = self._ensure_project_workspace(slug, proj["name"], proj.get("client", ""), proj.get("platform", "direct"))
            context_md = (proj_dir / "context.md").read_text(encoding="utf-8")
            try:
                specs_data = json.loads((proj_dir / "specs.json").read_text(encoding="utf-8"))
            except Exception:
                specs_data = {}

            return {
                "project": proj,
                "workspace_dir": str(proj_dir),
                "artifact_counts": artifact_counts,
                "total_artifacts": sum(artifact_counts.values()),
                "income_total": fin_totals.get("income", 0.0),
                "expense_total": fin_totals.get("expense", 0.0),
                "context_preview": context_md[:800],
                "specs": specs_data
            }

    def list_projects(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            if status:
                cursor.execute("SELECT * FROM projects WHERE status = ? ORDER BY is_active DESC, id DESC", (status,))
            else:
                cursor.execute("SELECT * FROM projects ORDER BY is_active DESC, id DESC")
            return [dict(row) for row in cursor.fetchall()]

    # ==========================================================
    # Phase 2.3 & 2.4: Artifacts & Semantic Vector Memory
    # ==========================================================
    def save_artifact(
        self,
        artifact_type: str,
        title: str,
        content: str,
        project_slug: Optional[str] = None,
        file_path: Optional[str] = None,
        tags: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        embedding: Optional[List[float]] = None,
        embedding_model: str = "local/ngram-128"
    ) -> Dict[str, Any]:
        project_id = None
        resolved_slug = project_slug or self._active_project_slug
        if resolved_slug:
            proj = self.create_or_get_project(resolved_slug)
            project_id = proj["id"]
            resolved_slug = proj["slug"]
        else:
            active = self.get_active_project()
            if active:
                project_id = active["id"]
                resolved_slug = active["slug"]

        meta_str = json.dumps(metadata or {}, ensure_ascii=False)

        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO vault_artifacts (project_id, type, title, content, metadata_json, file_path, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (project_id, artifact_type, title, content, meta_str, file_path, tags or ""))
            artifact_id = cursor.lastrowid

            # Index vector embedding automatically (using provided vector or local fallback)
            vec = embedding or compute_local_embedding(f"{title}\n{content}\n{tags or ''}")
            cursor.execute("""
            INSERT OR REPLACE INTO vault_embeddings (artifact_id, model, vector_json)
            VALUES (?, ?, ?)
            """, (artifact_id, embedding_model, json.dumps(vec)))

            conn.commit()
            cursor.execute("SELECT * FROM vault_artifacts WHERE id = ?", (artifact_id,))
            saved = dict(cursor.fetchone())

        # Append entry to project's context.md if linked to a project
        if resolved_slug:
            proj_dir = self.data_dir / "projects" / resolved_slug
            context_file = proj_dir / "context.md"
            if context_file.exists():
                timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
                entry = f"\n- **[{timestamp}] ({artifact_type.upper()}) {title}:** {content[:300]}\n"
                with open(context_file, "a", encoding="utf-8") as f:
                    f.write(entry)

        return saved

    def update_artifact_embedding(self, artifact_id: int, vector: List[float], model: str) -> None:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO vault_embeddings (artifact_id, model, vector_json)
            VALUES (?, ?, ?)
            """, (artifact_id, model, json.dumps(vector)))
            conn.commit()

    def search_vault(
        self,
        query: str,
        artifact_type: Optional[str] = None,
        project_slug: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            like_query = f"%{query}%"
            sql = """
                SELECT a.*, p.name as project_name, p.slug as project_slug
                FROM vault_artifacts a
                LEFT JOIN projects p ON a.project_id = p.id
                WHERE (a.title LIKE ? OR a.content LIKE ? OR a.tags LIKE ?)
            """
            params: List[Any] = [like_query, like_query, like_query]
            if artifact_type:
                sql += " AND a.type = ?"
                params.append(artifact_type)
            if project_slug:
                sql += " AND p.slug = ?"
                params.append(slugify_project(project_slug))
            sql += " ORDER BY a.id DESC LIMIT ?"
            params.append(limit)
            cursor.execute(sql, tuple(params))
            return [dict(row) for row in cursor.fetchall()]

    def semantic_search_vault(
        self,
        query: str,
        query_embedding: Optional[List[float]] = None,
        project_slug: Optional[str] = None,
        artifact_type: Optional[str] = None,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Phase 2.4 Semantic Vector Memory Search:
        Computes cosine similarity against stored embeddings in `vault_embeddings`
        plus keyword overlap boost so questions like:
        'What did the client say about button colors in project X?' retrieve exact matches.
        """
        with self._get_conn() as conn:
            cursor = conn.cursor()
            sql = """
                SELECT a.*, p.name as project_name, p.slug as project_slug, e.vector_json, e.model as emb_model
                FROM vault_artifacts a
                LEFT JOIN projects p ON a.project_id = p.id
                LEFT JOIN vault_embeddings e ON e.artifact_id = a.id
                WHERE 1=1
            """
            params: List[Any] = []
            if project_slug:
                sql += " AND p.slug = ?"
                params.append(slugify_project(project_slug))
            if artifact_type:
                sql += " AND a.type = ?"
                params.append(artifact_type)

            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall()

        local_q_vec = compute_local_embedding(query)
        q_tokens = {t.lower() for t in re.findall(r"[\w\u0600-\u06FF]{2,}", query)}
        scored: List[Dict[str, Any]] = []

        for r in rows:
            item = dict(r)
            vec_str = item.pop("vector_json", None)
            doc_vec: List[float] = []
            if vec_str:
                try:
                    doc_vec = json.loads(vec_str)
                except Exception:
                    doc_vec = []

            if query_embedding and doc_vec and len(query_embedding) == len(doc_vec):
                sim = _cosine_similarity(query_embedding, doc_vec)
            else:
                fallback_doc_vec = doc_vec if len(doc_vec) == len(local_q_vec) else compute_local_embedding(
                    f"{item.get('title', '')}\n{item.get('content', '')}\n{item.get('tags', '')}"
                )
                sim = _cosine_similarity(local_q_vec, fallback_doc_vec)

            # Lexical keyword overlap boost
            doc_text = f"{item.get('title', '')} {item.get('content', '')} {item.get('tags', '')}".lower()
            if q_tokens:
                matched_tokens = sum(1 for tok in q_tokens if tok in doc_text)
                lexical_boost = 0.25 * (matched_tokens / len(q_tokens))
            else:
                lexical_boost = 0.0

            item["similarity"] = round(min(1.0, max(0.0, sim + lexical_boost)), 4)
            scored.append(item)

        scored.sort(key=lambda x: x["similarity"], reverse=True)
        return scored[:top_k]

    # ==========================================================
    # Phase 2.2: Financial Ledger & Deduplication Engine
    # ==========================================================
    def record_transaction(
        self,
        amount: float,
        currency: str = "Toman",
        category: str = "income",
        tracking_code: Optional[str] = None,
        sender_card: str = "",
        receiver_card: str = "",
        bank_name: str = "",
        transfer_type: str = "",
        date: str = "",
        description: Optional[str] = None,
        receipt_path: Optional[str] = None,
        project_slug: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Records a financial transaction with tracking code deduplication.
        If `tracking_code` already exists in `financial_ledger`, returns the existing record
        with `duplicate=True` to prevent double-logging receipts.
        """
        clean_tracking = (tracking_code or "").strip() or None
        with self._get_conn() as conn:
            cursor = conn.cursor()
            if clean_tracking:
                cursor.execute(
                    "SELECT * FROM financial_ledger WHERE tracking_code = ? LIMIT 1",
                    (clean_tracking,)
                )
                existing = cursor.fetchone()
                if existing:
                    res = dict(existing)
                    res["duplicate"] = True
                    return res

            project_id = None
            resolved_slug = project_slug or self._active_project_slug
            if resolved_slug:
                proj = self.create_or_get_project(resolved_slug)
                project_id = proj["id"]

            tx_date = date or datetime.utcnow().strftime("%Y-%m-%d %H:%M")
            cursor.execute("""
            INSERT INTO financial_ledger (
                project_id, amount, currency, category, tracking_code,
                sender_card, receiver_card, bank_name, transfer_type,
                date, description, receipt_path
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                project_id, amount, currency, category, clean_tracking,
                sender_card, receiver_card, bank_name, transfer_type,
                tx_date, description or "", receipt_path or ""
            ))
            conn.commit()
            cursor.execute("SELECT * FROM financial_ledger WHERE id = ?", (cursor.lastrowid,))
            res = dict(cursor.fetchone())
            res["duplicate"] = False
            return res

    def get_financial_summary(
        self,
        days: int = 7,
        project_slug: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generates weekly (`days=7`) or monthly (`days=30`) income/expense summaries.
        Normalizes Rial to Toman (1 Toman = 10 Rial) for unified Toman totals alongside per-currency breakdown.
        """
        cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        with self._get_conn() as conn:
            cursor = conn.cursor()
            sql = """
                SELECT f.*, p.name as project_name, p.slug as project_slug
                FROM financial_ledger f
                LEFT JOIN projects p ON f.project_id = p.id
                WHERE f.created_at >= ?
            """
            params: List[Any] = [cutoff]
            if project_slug:
                sql += " AND p.slug = ?"
                params.append(slugify_project(project_slug))
            sql += " ORDER BY f.id DESC"
            cursor.execute(sql, tuple(params))
            rows = [dict(r) for r in cursor.fetchall()]

        income_toman = 0.0
        expense_toman = 0.0
        by_currency: Dict[str, Dict[str, float]] = {}

        for tx in rows:
            cur = tx.get("currency") or "Toman"
            cat = tx.get("category") or "income"
            amt = float(tx.get("amount") or 0.0)
            by_currency.setdefault(cur, {"income": 0.0, "expense": 0.0})
            by_currency[cur][cat] = by_currency[cur].get(cat, 0.0) + amt

            # Normalize to Toman for domestic totals
            if cur.lower() == "rial":
                amt_toman = amt / 10.0
            elif cur.lower() == "toman":
                amt_toman = amt
            else:
                amt_toman = 0.0

            if cat == "income":
                income_toman += amt_toman
            else:
                expense_toman += amt_toman

        return {
            "period_days": days,
            "transaction_count": len(rows),
            "income_toman": round(income_toman, 2),
            "expense_toman": round(expense_toman, 2),
            "net_toman": round(income_toman - expense_toman, 2),
            "by_currency": by_currency,
            "recent_transactions": rows[:15]
        }

    # ==========================================================
    # Phase 6: Health, Habits & Medical Lab Methods
    # ==========================================================
    def log_health_or_habit(
        self,
        log_type: str,
        metric_name: str,
        value: str,
        unit: str = "",
        notes: str = "",
        is_completed: bool = True
    ) -> Dict[str, Any]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO health_and_habits (type, metric_name, value, unit, is_completed, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (log_type, metric_name, str(value), unit, 1 if is_completed else 0, notes))
            conn.commit()
            cursor.execute("SELECT * FROM health_and_habits WHERE id = ?", (cursor.lastrowid,))
            return dict(cursor.fetchone())

    def get_recent_bio_logs(self, days: int = 1) -> List[Dict[str, Any]]:
        cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM health_and_habits WHERE logged_at >= ? ORDER BY id DESC",
                (cutoff,)
            )
            return [dict(r) for r in cursor.fetchall()]

    def record_lab_result(
        self,
        test_category: str,
        biomarker: str,
        value: float,
        unit: str = "",
        reference_min: Optional[float] = None,
        reference_max: Optional[float] = None,
        lab_date: str = "",
        source_file: str = "",
        notes: str = ""
    ) -> Dict[str, Any]:
        flag = "NORMAL"
        if reference_min is not None and value < reference_min:
            flag = "LOW"
        elif reference_max is not None and value > reference_max:
            flag = "HIGH"

        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO medical_lab_results (
                test_category, biomarker, value, unit,
                reference_min, reference_max, flag, lab_date, source_file, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                test_category, biomarker, value, unit,
                reference_min, reference_max, flag,
                lab_date or datetime.utcnow().strftime("%Y-%m-%d"),
                source_file, notes
            ))
            conn.commit()
            cursor.execute("SELECT * FROM medical_lab_results WHERE id = ?", (cursor.lastrowid,))
            return dict(cursor.fetchone())

    def get_lab_results(self, only_flagged: bool = False) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            if only_flagged:
                cursor.execute("SELECT * FROM medical_lab_results WHERE flag != 'NORMAL' ORDER BY id DESC")
            else:
                cursor.execute("SELECT * FROM medical_lab_results ORDER BY id DESC")
            return [dict(r) for r in cursor.fetchall()]

    # ==========================================================
    # Phase 3: Freelance Radar Persistence
    # ==========================================================
    def save_freelance_lead(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """Saves a scraped freelance project lead if not already seen."""
        ext_id = str(lead["external_id"])
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM freelance_leads WHERE external_id = ? LIMIT 1", (ext_id,))
            existing = cursor.fetchone()
            if existing:
                res = dict(existing)
                res["is_new"] = False
                return res

            cursor.execute("""
            INSERT INTO freelance_leads (
                external_id, platform, title, description, category,
                budget_min, budget_max, currency, employer_name, employer_rating,
                url, match_score, suggested_bid, suggested_timeline, proposal_draft, notified
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ext_id,
                lead.get("platform", "unknown"),
                lead.get("title", ""),
                lead.get("description", ""),
                lead.get("category", ""),
                float(lead.get("budget_min", 0.0)),
                float(lead.get("budget_max", 0.0)),
                lead.get("currency", "Toman"),
                lead.get("employer_name", ""),
                float(lead.get("employer_rating", 0.0)),
                lead.get("url", ""),
                int(lead.get("match_score", 0)),
                lead.get("suggested_bid", ""),
                lead.get("suggested_timeline", ""),
                lead.get("proposal_draft", ""),
                1 if lead.get("notified") else 0
            ))
            conn.commit()
            cursor.execute("SELECT * FROM freelance_leads WHERE id = ?", (cursor.lastrowid,))
            res = dict(cursor.fetchone())
            res["is_new"] = True
            return res

    def get_top_freelance_leads(self, min_score: int = 0, limit: int = 10) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM freelance_leads WHERE match_score >= ? ORDER BY match_score DESC, id DESC LIMIT ?",
                (min_score, limit)
            )
            return [dict(r) for r in cursor.fetchall()]


vault = ProjectVault()
