"""The single local account: password hashing (PBKDF2), sessions, and recovery by
security questions.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import time
from pathlib import Path

__all__ = [
    "Accounts", "MAX_USERS", "SESSION_HOURS", "MIN_PASSWORD",
    "MIN_QUESTIONS", "MAX_QUESTIONS", "MIN_ANSWER", "SUGGESTED_QUESTIONS",
    "SUGGESTED", "RECOVERY_ATTEMPTS", "RECOVERY_LOCK_MINUTES", "Refused",
    "normalise_answer",
]

MAX_USERS = 1
SESSION_HOURS = 12

_ITERATIONS = 600_000
_SALT_BYTES = 16

_NAME = re.compile(r"^[\w.-]{2,32}$")
MIN_PASSWORD = 8

MIN_QUESTIONS = 2
MAX_QUESTIONS = 5
MIN_ANSWER = 2

RECOVERY_ATTEMPTS = 5
RECOVERY_LOCK_MINUTES = 15

SUGGESTED_QUESTIONS = (
    "What was the name of your first pet?",
    "What street did you live on as a child?",
    "What was your first teacher called?",
    "What was the name of your first school?",
    "What was the make of your first car?",
    "A word or number only you would think of",
)

SUGGESTED = {
    "en": SUGGESTED_QUESTIONS,
    "ru": (
        "Как звали вашего первого питомца?",
        "На какой улице вы жили в детстве?",
        "Как звали вашего первого педагога?",
        "Как называлась ваша первая школа?",
        "Какой марки был ваш первый автомобиль?",
        "Слово или число, которое придёт в голову только вам",
    ),
}


def normalise_answer(text: str) -> str:
    return " ".join((text or "").split()).casefold()


class Refused(ValueError):
    def __init__(self, english: str, code: str, **values) -> None:
        super().__init__(english)
        self.code = code
        self.values = values


class Accounts:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.users: dict[str, dict] = {}
        self._sessions: dict[str, tuple[str, float]] = {}
        if self.path.exists():
            self.users = json.loads(self.path.read_text(encoding="utf-8"))


    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.users, indent=1, ensure_ascii=False), encoding="utf-8"
        )

    @property
    def empty(self) -> bool:
        return not self.users

    @property
    def full(self) -> bool:
        return len(self.users) >= MAX_USERS


    def add(self, name: str, password: str,
            recovery: "list[tuple[str, str]] | None" = None) -> None:
        name = (name or "").strip()
        if not _NAME.match(name):
            raise Refused(
                "a name is 2 to 32 characters: letters of any alphabet, digits, dot, "
                "dash or underscore",
                "name_shape",
            )
        if name.lower() in {u.lower() for u in self.users}:
            raise Refused(f"{name!r} is taken", "name_taken", name=name)
        if self.full:
            raise Refused(
                "this app holds at most one account, and it already exists"
                if MAX_USERS == 1
                else f"this app holds at most {MAX_USERS} accounts",
                "one_account" if MAX_USERS == 1 else "most_accounts",
                n=MAX_USERS,
            )
        if len(password or "") < MIN_PASSWORD:
            raise Refused(f"a password is at least {MIN_PASSWORD} characters",
                          "short_password", n=MIN_PASSWORD)

        pairs = _checked_recovery(recovery) if recovery else None

        salt = secrets.token_bytes(_SALT_BYTES)
        self.users[name] = {
            "salt": salt.hex(),
            "hash": _derive(password, salt).hex(),
            "iterations": _ITERATIONS,
            "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        if pairs:
            self.users[name]["recovery"] = _sealed(pairs)
        self._save()

    def remove(self, name: str) -> None:
        if name in self.users:
            del self.users[name]
            self._save()
            for token, (who, _) in list(self._sessions.items()):
                if who == name:
                    del self._sessions[token]


    @property
    def sole(self) -> str | None:
        return next(iter(self.users), None)

    def has_recovery(self, name: str | None = None) -> bool:
        record = self.users.get(name or self.sole or "") or {}
        return bool(record.get("recovery", {}).get("questions"))

    def recovery_questions(self, name: str | None = None) -> list[str]:
        record = self.users.get(name or self.sole or "") or {}
        return [q["ask"] for q in record.get("recovery", {}).get("questions", [])]

    def set_recovery(self, name: str, pairs: "list[tuple[str, str]]") -> None:
        if name not in self.users:
            raise Refused(f"no account named {name!r}", "no_account", name=name)
        self.users[name]["recovery"] = _sealed(_checked_recovery(pairs))
        self._save()

    def recovery_locked_for(self, name: str | None = None) -> int:
        record = self.users.get(name or self.sole or "") or {}
        until = record.get("recovery", {}).get("locked_until", 0)
        return max(0, int(until - time.time()))

    def reset_password(self, answers: "list[str]", new_password: str,
                       name: str | None = None) -> bool:
        who = name or self.sole
        record = self.users.get(who or "")
        if record is None or not record.get("recovery", {}).get("questions"):
            return False
        if self.recovery_locked_for(who):
            return False
        if len(new_password or "") < MIN_PASSWORD:
            raise Refused(f"a password is at least {MIN_PASSWORD} characters",
                          "short_password", n=MIN_PASSWORD)

        block = record["recovery"]
        questions = block["questions"]
        given = list(answers or [])
        right = len(given) == len(questions)
        for asked, answer in zip(questions, given + [""] * len(questions)):
            got = _derive(
                normalise_answer(answer),
                bytes.fromhex(asked["salt"]),
                asked.get("iterations", _ITERATIONS),
            )
            if not secrets.compare_digest(bytes.fromhex(asked["hash"]), got):
                right = False

        if not right:
            block["failed"] = int(block.get("failed", 0)) + 1
            if block["failed"] >= RECOVERY_ATTEMPTS:
                block["locked_until"] = time.time() + RECOVERY_LOCK_MINUTES * 60
                block["failed"] = 0
            self._save()
            return False

        salt = secrets.token_bytes(_SALT_BYTES)
        record["salt"] = salt.hex()
        record["hash"] = _derive(new_password, salt).hex()
        record["iterations"] = _ITERATIONS
        record["reset"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        block["failed"] = 0
        block["locked_until"] = 0
        self._save()
        for token, (holder, _) in list(self._sessions.items()):
            if holder == who:
                del self._sessions[token]
        return True


    def check(self, name: str, password: str) -> bool:
        record = self.users.get((name or "").strip())
        if record is None:
            _derive(password or "", b"\x00" * _SALT_BYTES)
            return False
        want = bytes.fromhex(record["hash"])
        got = _derive(
            password or "",
            bytes.fromhex(record["salt"]),
            record.get("iterations", _ITERATIONS),
        )
        return secrets.compare_digest(want, got)

    def start_session(self, name: str) -> str:
        token = secrets.token_urlsafe(32)
        self._sessions[token] = (name, time.time() + SESSION_HOURS * 3600)
        return token

    def whoami(self, token: str | None) -> str | None:
        if not token:
            return None
        found = self._sessions.get(token)
        if found is None:
            return None
        name, expires = found
        if time.time() > expires:
            del self._sessions[token]
            return None
        return name

    def end_session(self, token: str | None) -> None:
        if token:
            self._sessions.pop(token, None)


def _checked_recovery(pairs: "list[tuple[str, str]]") -> "list[tuple[str, str]]":
    kept = [
        (" ".join(str(q).split()), str(a))
        for q, a in (pairs or [])
        if " ".join(str(q).split()) and normalise_answer(a)
    ]
    if len(kept) < MIN_QUESTIONS:
        raise Refused(
            f"give at least {MIN_QUESTIONS} questions, each with an answer",
            "few_questions", n=MIN_QUESTIONS,
        )
    if len(kept) > MAX_QUESTIONS:
        raise Refused(f"at most {MAX_QUESTIONS} questions", "many_questions",
                      n=MAX_QUESTIONS)
    for question, answer in kept:
        if len(normalise_answer(answer)) < MIN_ANSWER:
            raise Refused(
                f"the answer to {question!r} is too short to be worth asking",
                "short_answer", question=question,
            )
    asked = [q.casefold() for q, _ in kept]
    if len(set(asked)) != len(asked):
        raise Refused("two of those questions are the same", "same_questions")
    return kept


def _sealed(pairs: "list[tuple[str, str]]") -> dict:
    questions = []
    for question, answer in pairs:
        salt = secrets.token_bytes(_SALT_BYTES)
        questions.append({
            "ask": question,
            "salt": salt.hex(),
            "hash": _derive(normalise_answer(answer), salt).hex(),
            "iterations": _ITERATIONS,
        })
    return {"questions": questions, "failed": 0, "locked_until": 0}


def _derive(password: str, salt: bytes, iterations: int | None = None) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt,
        _ITERATIONS if iterations is None else iterations,
    )
