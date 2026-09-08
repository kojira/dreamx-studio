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
                BEGIN IMMEDIATE;
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
                CREATE TABLE IF NOT EXISTS operations (
                    slot INTEGER PRIMARY KEY CHECK(slot=1), kind TEXT NOT NULL,
                    owner_id TEXT NOT NULL, container_id TEXT, started_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS video_inputs (
                    id TEXT PRIMARY KEY, state TEXT NOT NULL, created_at TEXT NOT NULL,
                    width INTEGER, height INTEGER, duration_seconds REAL, source_fps REAL,
                    normalized_frames INTEGER, has_audio INTEGER, raw_sha256 TEXT, normalized_sha256 TEXT
                );
                COMMIT;
            ''')
            db.execute('BEGIN IMMEDIATE')
            if 'normalized_fps' not in {r['name'] for r in db.execute('PRAGMA table_info(video_inputs)')}:
                db.execute('ALTER TABLE video_inputs ADD COLUMN normalized_fps REAL NOT NULL DEFAULT 24')

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
            if db.execute('SELECT 1 FROM operations').fetchone():
                raise Busy('An operation is active')
            if db.execute("SELECT 1 FROM jobs WHERE state IN ('admitted','preparing','generating','muxing','cancelling')").fetchone():
                raise Busy('An inference job is active')
            job_id = str(uuid.uuid4()); stamp = now()
            db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?)',
                       (job_id, request_id, 'admitted', serialized, stamp, stamp, None))
            db.execute('INSERT INTO operations VALUES (1,?,?,NULL,?)', (job_kind(payload),job_id,stamp))
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
            if state in TERMINAL:
                db.execute('DELETE FROM operations WHERE owner_id=? AND container_id IS NULL',(job_id,))

    def recover_after_worker_reconciliation(self):
        """Call ONLY after the runner confirms prior workers are stopped.

        Database restart alone must not release the active inference slot while
        an old container may still be running.
        """
        with self.connect() as db:
            cursor = db.execute("UPDATE jobs SET state='interrupted',updated_at=?,error_code='SERVICE_RESTART' WHERE state IN ('admitted','preparing','generating','muxing','cancelling')", (now(),))
            db.execute("UPDATE video_inputs SET state='failed' WHERE state IN ('uploading','validating')")
            db.execute('DELETE FROM operations')
            return cursor.rowcount

    def operation(self):
        with self.connect() as db:
            row=db.execute('SELECT * FROM operations').fetchone()
            return dict(row) if row else None

    def reserve_validation(self, input_id):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM operations').fetchone() or db.execute("SELECT 1 FROM jobs WHERE state IN ('admitted','preparing','generating','muxing','cancelling')").fetchone():
                raise Busy('BUSY')
            row=db.execute('SELECT state FROM video_inputs WHERE id=?',(input_id,)).fetchone()
            if not row or row['state']!='uploading':raise Conflict('INVALID_VIDEO')
            db.execute('INSERT INTO operations VALUES (1,?,?,NULL,?)',('validate_video',input_id,now()))
            db.execute("UPDATE video_inputs SET state='validating' WHERE id=?",(input_id,))

    def bind_container(self, owner_id, container_id):
        with self.connect() as db:
            if db.execute('UPDATE operations SET container_id=? WHERE owner_id=? AND container_id IS NULL',(container_id,owner_id)).rowcount!=1:
                raise Conflict('Lease ownership mismatch')

    def release_stopped(self, owner_id):
        """Caller must independently confirm the exact container is stopped."""
        with self.connect() as db:db.execute('DELETE FROM operations WHERE owner_id=?',(owner_id,))

    def video(self, input_id):
        with self.connect() as db:
            row=db.execute('SELECT * FROM video_inputs WHERE id=?',(input_id,)).fetchone()
            if not row:raise KeyError(input_id)
            return dict(row)

    def reserve_upload(self, input_id):
        with self.connect() as db:
            db.execute('INSERT INTO video_inputs (id,state,created_at) VALUES (?,?,?)',(input_id,'uploading',now()))

    def fail_video(self, input_id):
        with self.connect() as db:
            db.execute("UPDATE video_inputs SET state='failed' WHERE id=? AND state!='validated'",(input_id,))

    def finish_video(self, input_id, metadata):
        metadata = {'normalized_fps': 24, **metadata}
        keys=('width','height','duration_seconds','source_fps','normalized_frames','has_audio','raw_sha256','normalized_sha256','normalized_fps')
        with self.connect() as db:
            if db.execute("UPDATE video_inputs SET state='validated',"+','.join(k+'=?' for k in keys)+" WHERE id=? AND state='validating'",(*[metadata[k] for k in keys],input_id)).rowcount!=1:
                raise Conflict('Input no longer validating')


def job_kind(payload):
    return 'operator_test' if 'operator_test' in payload else payload.get('kind','generate')
