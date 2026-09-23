import os
import requests

TURSO_URL = os.getenv("TURSO_DATABASE_URL")
TURSO_TOKEN = os.getenv("TURSO_AUTH_TOKEN")

_TURSO_HTTP = TURSO_URL.replace("libsql://", "https://").rstrip("/")
_TURSO_HEADERS = {
    "Authorization": f"Bearer {TURSO_TOKEN}",
    "Content-Type": "application/json",
}


def _to_arg(v):
    if v is None:
        return {"type": "null"}
    if isinstance(v, bool):
        return {"type": "integer", "value": "1" if v else "0"}
    if isinstance(v, int):
        return {"type": "integer", "value": str(v)}
    if isinstance(v, float):
        return {"type": "float", "value": str(v)}
    return {"type": "text", "value": str(v)}


def _unwrap(cell):
    if isinstance(cell, dict):
        return cell.get("value")
    return cell


def db_execute(sql, args=None):
    stmt = {"sql": sql}
    if args:
        stmt["args"] = [_to_arg(a) for a in args]
    body = {"requests": [{"type": "execute", "stmt": stmt}, {"type": "close"}]}
    try:
        r = requests.post(
            f"{_TURSO_HTTP}/v2/pipeline",
            headers=_TURSO_HEADERS, json=body, timeout=30,
        )
        if r.status_code != 200:
            print(f"Ошибка HTTP БД: {r.status_code} {r.text[:200]}")
            return None
        data = r.json()
        first = data.get("results", [{}])[0]
        if first.get("type") == "error":
            print(f"Ошибка SQL: {first}")
            return None
        response = first.get("response", {}).get("result", {})
        return {
            "rows": response.get("rows", []),
            "cols": [c.get("name") for c in response.get("cols", [])],
        }
    except Exception as e:
        print(f"Ошибка БД: {e}")
        return None


def init_db():
    print("init_db: создаю таблицу...")
    db_execute("""
        CREATE TABLE IF NOT EXISTS citizens (
            user_id      INTEGER PRIMARY KEY,
            citizen_uuid TEXT UNIQUE NOT NULL,
            issue_date   TEXT NOT NULL,
            full_name    TEXT,
            birth_date   TEXT
        )
    """)


def get_passport(uid):
    r = db_execute(
        "SELECT user_id, citizen_uuid, issue_date, full_name, birth_date "
        "FROM citizens WHERE user_id = ?", [uid]
    )
    if not r or not r.get("rows"):
        return None
    row = r["rows"][0]
    return {
        "user_id": int(_unwrap(row[0])),
        "citizen_uuid": _unwrap(row[1]),
        "issue_date": _unwrap(row[2]),
        "full_name": _unwrap(row[3]),
        "birth_date": _unwrap(row[4]),
    }


def get_passport_by_uuid(uuid_str):
    r = db_execute(
        "SELECT user_id, citizen_uuid, issue_date, full_name, birth_date "
        "FROM citizens WHERE citizen_uuid = ?", [uuid_str]
    )
    if not r or not r.get("rows"):
        return None
    row = r["rows"][0]
    return {
        "user_id": int(_unwrap(row[0])),
        "citizen_uuid": _unwrap(row[1]),
        "issue_date": _unwrap(row[2]),
        "full_name": _unwrap(row[3]),
        "birth_date": _unwrap(row[4]),
    }


def create_passport(uid, citizen_uuid, issue_date, full_name, birth_date):
    db_execute(
        "INSERT INTO citizens "
        "(user_id, citizen_uuid, issue_date, full_name, birth_date) "
        "VALUES (?, ?, ?, ?, ?)",
        [uid, citizen_uuid, issue_date, full_name, birth_date]
    )


def update_passport(uid, field, value):
    if field not in ("full_name", "birth_date"):
        raise ValueError("Недопустимое поле")
    db_execute(f"UPDATE citizens SET {field} = ? WHERE user_id = ?",
               [value, uid])