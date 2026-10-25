"""
Group Mode storage: rooms and members in a small SQLite database.

A room moves through these stages:
    lobby      -> people join with the room code
    answering  -> each member answers their own questions
    searching  -> Puss is finding places for everyone (a few seconds)
    voting     -> members vote on up to 3 places
    done       -> the winner is revealed

Members prove who they are with a private token (only its hash is stored),
sent in the X-Member-Token header. Rooms are deleted after a day.
"""

import hashlib
import json
import os
import secrets
import sqlite3
import threading
import time
from pathlib import Path

DB_PATH = os.getenv("GROUPS_DB", str(Path(__file__).with_name("data") / "groups.db"))
ROOM_TTL_SECONDS = 24 * 3600
MAX_MEMBERS = 8
QUESTIONS_PER_MEMBER = 3
# If the server restarts mid-search, let the host try again after this long.
SEARCH_TIMEOUT_SECONDS = 120
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I mix-ups


class GroupError(Exception):
    """An error to show the player, with the HTTP status to use."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _now():
    return time.time()


SCHEMA = """
CREATE TABLE IF NOT EXISTS rooms (
    id          TEXT PRIMARY KEY,
    code        TEXT UNIQUE NOT NULL,
    city        TEXT NOT NULL,
    status      TEXT NOT NULL,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL,
    results     TEXT,
    winner      INTEGER,
    message     TEXT
);
CREATE TABLE IF NOT EXISTS members (
    id          TEXT PRIMARY KEY,
    room_id     TEXT NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    token_hash  TEXT NOT NULL,
    is_host     INTEGER NOT NULL DEFAULT 0,
    joined_at   REAL NOT NULL,
    history     TEXT NOT NULL DEFAULT '[]',
    pending     TEXT,
    done        INTEGER NOT NULL DEFAULT 0,
    vote        INTEGER
);
CREATE INDEX IF NOT EXISTS members_room ON members(room_id);
"""


class GroupStore:
    def __init__(self, path=DB_PATH):
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        # One shared connection, guarded by the lock (uvicorn runs our sync
        # endpoints on worker threads).
        self._db = sqlite3.connect(path, check_same_thread=False, timeout=10)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        if path != ":memory:":
            self._db.execute("PRAGMA journal_mode = WAL")
        self._db.executescript(SCHEMA)
        self._db.commit()

    # -- helpers -------------------------------------------------------------

    def _room(self, room_id):
        row = self._db.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
        if row is None or row["created_at"] < _now() - ROOM_TTL_SECONDS:
            raise GroupError(404, "This party no longer exists. Start a new one!")
        return row

    def _members(self, room_id):
        return self._db.execute(
            "SELECT * FROM members WHERE room_id = ? ORDER BY joined_at", (room_id,)
        ).fetchall()

    def _touch(self, room_id, **fields):
        fields["updated_at"] = _now()
        cols = ", ".join(f"{k} = ?" for k in fields)
        self._db.execute(f"UPDATE rooms SET {cols} WHERE id = ?", (*fields.values(), room_id))

    def _new_member(self, room_id, name, is_host):
        token = secrets.token_urlsafe(24)
        member_id = secrets.token_urlsafe(8)
        self._db.execute(
            "INSERT INTO members (id, room_id, name, token_hash, is_host, joined_at) VALUES (?, ?, ?, ?, ?, ?)",
            (member_id, room_id, name, _hash(token), int(is_host), _now()),
        )
        return member_id, token

    def _unique_name(self, room_id, name):
        taken = {m["name"].lower() for m in self._members(room_id)}
        if name.lower() not in taken:
            return name
        n = 2
        while f"{name} {n}".lower() in taken:
            n += 1
        return f"{name} {n}"

    def _cleanup(self):
        self._db.execute("DELETE FROM rooms WHERE created_at < ?", (_now() - ROOM_TTL_SECONDS,))

    # -- rooms and members ---------------------------------------------------

    def create_room(self, name, city):
        with self._lock:
            self._cleanup()
            room_id = secrets.token_urlsafe(9)
            for _ in range(20):
                code = "VIBE-" + "".join(secrets.choice(CODE_ALPHABET) for _ in range(4))
                if not self._db.execute("SELECT 1 FROM rooms WHERE code = ?", (code,)).fetchone():
                    break
            else:
                raise GroupError(503, "Couldn't make a room code. Try again.")
            now = _now()
            self._db.execute(
                "INSERT INTO rooms (id, code, city, status, created_at, updated_at) VALUES (?, ?, ?, 'lobby', ?, ?)",
                (room_id, code, city, now, now),
            )
            member_id, token = self._new_member(room_id, name, is_host=True)
            self._db.commit()
            return {"room_id": room_id, "code": code, "member_id": member_id, "member_token": token}

    def join_room(self, code, name):
        code = code.strip().upper()
        if code and not code.startswith("VIBE-"):
            code = "VIBE-" + code
        with self._lock:
            row = self._db.execute("SELECT * FROM rooms WHERE code = ?", (code,)).fetchone()
            if row is None or row["created_at"] < _now() - ROOM_TTL_SECONDS:
                raise GroupError(404, "No party with that code. Check the letters and try again.")
            if row["status"] not in ("lobby", "answering"):
                raise GroupError(409, "This party has already picked its places. Ask the host to start a new one.")
            if len(self._members(row["id"])) >= MAX_MEMBERS:
                raise GroupError(409, f"This party is full ({MAX_MEMBERS} people max).")
            member_id, token = self._new_member(row["id"], self._unique_name(row["id"], name), is_host=False)
            self._touch(row["id"])
            self._db.commit()
            return {"room_id": row["id"], "code": row["code"], "member_id": member_id, "member_token": token}

    def authenticate(self, room_id, token):
        if not token:
            raise GroupError(401, "You're not part of this party. Join with the room code.")
        with self._lock:
            self._room(room_id)
            member = self._db.execute(
                "SELECT * FROM members WHERE room_id = ? AND token_hash = ?", (room_id, _hash(token))
            ).fetchone()
            if member is None:
                raise GroupError(401, "You're not part of this party. Join with the room code.")
            return dict(member)

    def state(self, room_id, member_id):
        """Everything the room page needs, from this member's point of view."""
        with self._lock:
            room = self._room(room_id)
            if room["status"] == "searching" and room["updated_at"] < _now() - SEARCH_TIMEOUT_SECONDS:
                self._touch(room_id, status="answering", message="The search timed out. The host can try again.")
                self._db.commit()
                room = self._room(room_id)
            members = self._members(room_id)
            results = json.loads(room["results"]) if room["results"] else []
            votes = [0] * len(results)
            for m in members:
                if m["vote"] is not None and 0 <= m["vote"] < len(votes):
                    votes[m["vote"]] += 1
            me = next(m for m in members if m["id"] == member_id)
            return {
                "room_id": room_id,
                "code": room["code"],
                "city": room["city"],
                "status": room["status"],
                "message": room["message"],
                "questions_per_member": QUESTIONS_PER_MEMBER,
                "me": {
                    "id": me["id"],
                    "name": me["name"],
                    "is_host": bool(me["is_host"]),
                    "done": bool(me["done"]),
                    "answered": len(json.loads(me["history"])),
                    "vote": me["vote"],
                },
                "members": [
                    {
                        "id": m["id"],
                        "name": m["name"],
                        "is_host": bool(m["is_host"]),
                        "done": bool(m["done"]),
                        "answered": len(json.loads(m["history"])),
                        "voted": m["vote"] is not None,
                    }
                    for m in members
                ],
                "results": [{**r, "votes": votes[i]} for i, r in enumerate(results)],
                "winner": room["winner"],
            }

    # -- game flow -------------------------------------------------------------

    def start(self, room_id, member):
        with self._lock:
            room = self._room(room_id)
            if not member["is_host"]:
                raise GroupError(403, "Only the host can start the quest.")
            if room["status"] != "lobby":
                return
            self._touch(room_id, status="answering", message=None)
            self._db.commit()

    def answer_and_get_pending(self, room_id, member_id, question, answer):
        """
        Record an answer to this member's pending question (if it matches),
        then return (history, pending_question, done).
        """
        with self._lock:
            room = self._room(room_id)
            if room["status"] != "answering":
                raise GroupError(409, "Questions are closed for this party.")
            m = self._db.execute("SELECT * FROM members WHERE id = ?", (member_id,)).fetchone()
            history = json.loads(m["history"])
            pending = json.loads(m["pending"]) if m["pending"] else None
            done = bool(m["done"])
            # Only accept an answer to the question we actually asked (stops
            # double-clicks from recording two answers).
            if answer and pending and not done and question == pending["question"]:
                history.append({"question": pending["question"], "answer": answer})
                pending = None
                done = len(history) >= QUESTIONS_PER_MEMBER
                self._db.execute(
                    "UPDATE members SET history = ?, pending = NULL, done = ? WHERE id = ?",
                    (json.dumps(history), int(done), member_id),
                )
                self._touch(room_id)
                self._db.commit()
            return history, pending, done

    def set_pending(self, member_id, question):
        with self._lock:
            row = self._db.execute("SELECT pending FROM members WHERE id = ?", (member_id,)).fetchone()
            if row["pending"]:  # another request got there first; keep theirs
                return json.loads(row["pending"])
            self._db.execute("UPDATE members SET pending = ? WHERE id = ?", (json.dumps(question), member_id))
            self._db.commit()
            return question

    def everyone_done(self, room_id):
        with self._lock:
            return all(m["done"] for m in self._members(room_id))

    def begin_search(self, room_id, member=None):
        """
        Move answering -> searching. Returns the city and the answers of
        everyone who finished, or None if someone else already started it.
        If `member` is given, they must be the host (an early start).
        """
        with self._lock:
            room = self._room(room_id)
            if member is not None and not member["is_host"]:
                raise GroupError(403, "Only the host can start the search early.")
            finished = [
                {"name": m["name"], "history": json.loads(m["history"])}
                for m in self._members(room_id) if m["done"]
            ]
            if room["status"] != "answering":
                return None
            if not finished:
                raise GroupError(409, "Wait until at least one person has finished their questions.")
            cur = self._db.execute(
                "UPDATE rooms SET status = 'searching', message = NULL, updated_at = ? WHERE id = ? AND status = 'answering'",
                (_now(), room_id),
            )
            self._db.commit()
            if cur.rowcount != 1:
                return None
            return {"city": room["city"], "members": finished}

    def save_results(self, room_id, results):
        with self._lock:
            if results:
                self._touch(room_id, status="voting", results=json.dumps(results), message=None)
            else:
                self._touch(
                    room_id, status="answering",
                    message="Puss couldn't find places matching everyone. The host can try again.",
                )
            self._db.commit()

    def search_failed(self, room_id):
        with self._lock:
            self._touch(room_id, status="answering", message="Something went wrong while searching. The host can try again.")
            self._db.commit()

    def vote(self, room_id, member_id, index):
        with self._lock:
            room = self._room(room_id)
            if room["status"] != "voting":
                raise GroupError(409, "Voting isn't open right now.")
            results = json.loads(room["results"])
            if not 0 <= index < len(results):
                raise GroupError(400, "That isn't one of the options.")
            self._db.execute("UPDATE members SET vote = ? WHERE id = ?", (index, member_id))
            self._touch(room_id)
            if all(m["vote"] is not None for m in self._members(room_id)):
                self._finish(room_id, len(results))
            self._db.commit()

    def reveal(self, room_id, member):
        with self._lock:
            room = self._room(room_id)
            if not member["is_host"]:
                raise GroupError(403, "Only the host can reveal the winner early.")
            if room["status"] != "voting":
                return
            self._finish(room_id, len(json.loads(room["results"])))
            self._db.commit()

    def _finish(self, room_id, n_results):
        tally = [0] * n_results
        for m in self._members(room_id):
            if m["vote"] is not None and 0 <= m["vote"] < n_results:
                tally[m["vote"]] += 1
        # Most votes wins; ties go to the higher-ranked pick (lower index).
        winner = max(range(n_results), key=lambda i: (tally[i], -i))
        self._touch(room_id, status="done", winner=winner)
