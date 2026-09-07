"""Transactional single-worker job state, independent of web framework."""
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

ACTIVE = ('admitted', 'preparing', 'generating', 'muxing', 'cancelling')
TERMINAL = ('succeeded', 'failed', 'cancelled', 'interrupted')
TRANSITIONS = {
    'admitted': {'preparing', 'cancelling', 'failed', 'interrupted'},
    'preparing': {'generating', 'cancelling', 'failed', 'interrupted'},
    'generating': {'muxing', 'cancelling', 'failed', 'interrupted'},
    'muxing': {'succeeded', 'cancelling', 'failed', 'interrupted'},
    'cancelling': {'cancelled', 'failed', 'interrupted'},
}

class Busy(Exception): pass
class Conflict(Exception): pass

def now():
    return datetime.now(timezone.utc).isoformat()

class Jobs:
    def __init__(self, path: Path):
        self.path = path
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL UNIQUE,
                    state TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    error_code TEXT
                );
                CREATE UNIQUE INDEX IF NOT EXISTS one_active ON jobs ((1))
                WHERE state IN ('admitted','preparing','generating','muxing','cancelling');
            ''')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        return db

    def create(self, request_id: str, payload: dict):
        serialized = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            prior = db.execute('SELECT * FROM jobs WHERE request_id=?', (request_id,)).fetchone()
            if prior:
                if prior['payload'] != serialized:
                    raise Conflict('Request ID reused with different parameters')
                return dict(prior), False
            if db.execute("SELECT 1 FROM jobs WHERE state IN ('admitted','preparing','generating','muxing','cancelling')").fetchone():
                raise Busy('An inference job is active')
            job_id = str(uuid.uuid4()); stamp = now()
            db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?)',
                       (job_id, request_id, 'admitted', serialized, stamp, stamp, None))
            return dict(db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()), True

    def get(self, job_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
            if row is None: raise KeyError(job_id)
            return dict(row)

    def transition(self, job_id, state, error_code=None):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT state FROM jobs WHERE id=?', (job_id,)).fetchone()
            if row is None: raise KeyError(job_id)
            old = row['state']
            if state not in TRANSITIONS.get(old, set()):
                raise Conflict(f'Invalid transition {old} -> {state}')
            db.execute('UPDATE jobs SET state=?, updated_at=?, error_code=? WHERE id=?',
                       (state, now(), error_code, job_id))

    def recover_after_worker_reconciliation(self):
        """Call ONLY after the runner confirms prior workers are stopped.

        Database restart alone must not release the active inference slot while
        an old container may still be running.
        """
        with self.connect() as db:
            cursor = db.execute("UPDATE jobs SET state='interrupted',updated_at=?,error_code='SERVICE_RESTART' WHERE state IN ('admitted','preparing','generating','muxing','cancelling')", (now(),))
            return cursor.rowcount
