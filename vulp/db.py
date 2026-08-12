"""SQLite-backed local package index."""
import sqlite3
import os
import json
from datetime import datetime

from .config import INDEX_DB, ensure_dirs


SCHEMA = """
CREATE TABLE IF NOT EXISTS packages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name   TEXT NOT NULL,           -- owner/repo
    name        TEXT NOT NULL,            -- repo name
    owner       TEXT NOT NULL,
    description TEXT,
    latest_tag  TEXT,
    stars       INTEGER DEFAULT 0,
    updated_at  TEXT,
    source      TEXT DEFAULT 'github',     -- 'github', 'local', etc.
    meta        TEXT,                      -- JSON blob
    UNIQUE(full_name)
);

CREATE TABLE IF NOT EXISTS versions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    pkg_id      INTEGER NOT NULL,
    tag         TEXT NOT NULL,
    tarball_url TEXT,
    zipball_url TEXT,
    published_at TEXT,
    size_bytes  INTEGER,
    vulpin_file TEXT,                     -- path to main .vul file in release
    deps        TEXT,                     -- JSON: {"pkg": "version", ...}
    FOREIGN KEY (pkg_id) REFERENCES packages(id),
    UNIQUE(pkg_id, tag)
);

CREATE TABLE IF NOT EXISTS cache_entries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name   TEXT NOT NULL,
    tag         TEXT NOT NULL,
    local_path  TEXT NOT NULL,
    downloaded_at TEXT,
    size_bytes  INTEGER,
    checksum    TEXT,
    UNIQUE(full_name, tag)
);

CREATE INDEX IF NOT EXISTS idx_pkg_name ON packages(name);
CREATE INDEX IF NOT EXISTS idx_pkg_owner ON packages(owner);
CREATE INDEX IF NOT EXISTS idx_ver_pkg  ON versions(pkg_id);
CREATE INDEX IF NOT EXISTS idx_cache_name ON cache_entries(full_name);
"""


class IndexDB:
    def __init__(self, path=None):
        ensure_dirs()
        self.path = path or INDEX_DB
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    # --- Packages ---

    def upsert_package(self, full_name, name, owner, description=None,
                       latest_tag=None, stars=0, updated_at=None, meta=None):
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO packages (full_name, name, owner, description, latest_tag, stars, updated_at, meta)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(full_name) DO UPDATE SET
                    description=excluded.description,
                    latest_tag=excluded.latest_tag,
                    stars=excluded.stars,
                    updated_at=excluded.updated_at,
                    meta=excluded.meta
            """, (full_name, name, owner, description, latest_tag, stars,
                  updated_at or datetime.utcnow().isoformat(),
                  json.dumps(meta) if meta else None))
            conn.commit()
            return conn.execute("SELECT id FROM packages WHERE full_name=?", (full_name,)).fetchone()["id"]

    def get_package(self, full_name):
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM packages WHERE full_name=?", (full_name,)).fetchone()
            return dict(row) if row else None

    def search_packages(self, query, limit=20):
        with self._connect() as conn:
            pattern = f"%{query}%"
            rows = conn.execute("""
                SELECT * FROM packages
                WHERE full_name LIKE ? OR name LIKE ? OR description LIKE ?
                ORDER BY stars DESC
                LIMIT ?
            """, (pattern, pattern, pattern, limit)).fetchall()
            return [dict(r) for r in rows]

    def list_packages(self, limit=100):
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM packages ORDER BY stars DESC LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in rows]

    # --- Versions ---

    def upsert_version(self, pkg_id, tag, tarball_url=None, zipball_url=None,
                       published_at=None, size_bytes=None, vulpin_file=None, deps=None):
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO versions (pkg_id, tag, tarball_url, zipball_url, published_at, size_bytes, vulpin_file, deps)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(pkg_id, tag) DO UPDATE SET
                    tarball_url=excluded.tarball_url,
                    zipball_url=excluded.zipball_url,
                    published_at=excluded.published_at,
                    size_bytes=excluded.size_bytes,
                    vulpin_file=excluded.vulpin_file,
                    deps=excluded.deps
            """, (pkg_id, tag, tarball_url, zipball_url, published_at,
                  size_bytes, vulpin_file, json.dumps(deps) if deps else None))
            conn.commit()

    def get_version(self, pkg_id, tag):
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM versions WHERE pkg_id=? AND tag=?", (pkg_id, tag)).fetchone()
            return dict(row) if row else None

    def get_versions(self, pkg_id):
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM versions WHERE pkg_id=? ORDER BY published_at DESC", (pkg_id,)).fetchall()
            return [dict(r) for r in rows]

    def get_latest_version(self, pkg_id):
        with self._connect() as conn:
            row = conn.execute("""
                SELECT * FROM versions WHERE pkg_id=? ORDER BY published_at DESC LIMIT 1
            """, (pkg_id,)).fetchone()
            return dict(row) if row else None

    # --- Cache ---

    def add_cache(self, full_name, tag, local_path, size_bytes=None, checksum=None):
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO cache_entries (full_name, tag, local_path, downloaded_at, size_bytes, checksum)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(full_name, tag) DO UPDATE SET
                    local_path=excluded.local_path,
                    downloaded_at=excluded.downloaded_at,
                    size_bytes=excluded.size_bytes,
                    checksum=excluded.checksum
            """, (full_name, tag, local_path, datetime.utcnow().isoformat(), size_bytes, checksum))
            conn.commit()

    def get_cache(self, full_name, tag):
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM cache_entries WHERE full_name=? AND tag=?", (full_name, tag)).fetchone()
            return dict(row) if row else None

    def list_cache(self):
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM cache_entries ORDER BY downloaded_at DESC").fetchall()
            return [dict(r) for r in rows]

    def remove_cache(self, full_name, tag=None):
        with self._connect() as conn:
            if tag:
                conn.execute("DELETE FROM cache_entries WHERE full_name=? AND tag=?", (full_name, tag))
            else:
                conn.execute("DELETE FROM cache_entries WHERE full_name=?", (full_name,))
            conn.commit()

    def clear_cache(self):
        with self._connect() as conn:
            conn.execute("DELETE FROM cache_entries")
            conn.commit()
