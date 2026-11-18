from __future__ import annotations
import json
from pathlib import Path
import sqlite3

class Store:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS runs (digest TEXT PRIMARY KEY, run_id TEXT NOT NULL, result TEXT NOT NULL)")
            # 批次结果按 (kind, digest) 唯一：同一批次失败重试只入账一次。
            db.execute("CREATE TABLE IF NOT EXISTS batches ("
                       "kind TEXT NOT NULL, digest TEXT NOT NULL, run_id TEXT NOT NULL, "
                       "result TEXT NOT NULL, PRIMARY KEY (kind, digest))")
            # 批次内每条原始行都留档，待核对请求可凭 request_id 查回。
            db.execute("CREATE TABLE IF NOT EXISTS batch_lines ("
                       "kind TEXT NOT NULL, digest TEXT NOT NULL, source_line INTEGER NOT NULL, "
                       "payload TEXT NOT NULL, PRIMARY KEY (kind, digest, source_line))")
            # 待核对索引：key 唯一标识一个请求分组，指向 batch_lines 里的原始行，
            # 不复制也不丢记录；无业务编号的分组用自己的键，不会互相覆盖。
            db.execute("CREATE TABLE IF NOT EXISTS pending_evidence ("
                       "kind TEXT NOT NULL, digest TEXT NOT NULL, request_key TEXT NOT NULL, "
                       "request_id TEXT NOT NULL, payload TEXT NOT NULL, "
                       "PRIMARY KEY (kind, digest, request_key))")

    def connect(self):
        return sqlite3.connect(self.path)

    def record(self, digest: str, run_id: str, result: dict) -> dict:
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO runs VALUES (?, ?, ?)",
                       (digest, run_id, json.dumps(result, ensure_ascii=False, sort_keys=True)))
            row = db.execute("SELECT run_id, result FROM runs WHERE digest=?", (digest,)).fetchone()
        return {"run_id": row[0], "result": json.loads(row[1])}

    def batch_run_id(self, digest: str) -> str:
        """批次编号由输入摘要派生，重试天然复用同一个编号。"""
        return "run-" + digest[:12]

    def record_batch(self, kind: str, digest: str, result: dict,
                     lines: list[dict] | None = None,
                     pending: list[dict] | None = None, run_id: str | None = None) -> dict:
        """原子写入批次结果、原始行与待核对索引。

        三者在同一事务内提交；主键冲突时回读既有结果，因此重试不会重复入账，
        也不会留下半条批次或丢行。
        """
        rid = run_id or self.batch_run_id(digest)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for index, line in enumerate(lines or []):
                source_line = line.get("source_line")
                if not isinstance(source_line, int):
                    source_line = index + 1
                db.execute("INSERT OR IGNORE INTO batch_lines (kind, digest, source_line, payload) "
                           "VALUES (?, ?, ?, ?)",
                           (kind, digest, source_line,
                            json.dumps(line, ensure_ascii=False, sort_keys=True)))
            for item in pending or []:
                request_key = str(item.get("key") or item.get("request_id") or "")
                db.execute("INSERT OR IGNORE INTO pending_evidence "
                           "(kind, digest, request_key, request_id, payload) VALUES (?, ?, ?, ?, ?)",
                           (kind, digest, request_key, str(item.get("request_id", "")),
                            json.dumps(item, ensure_ascii=False, sort_keys=True)))
            db.execute("INSERT OR IGNORE INTO batches (kind, digest, run_id, result) VALUES (?, ?, ?, ?)",
                       (kind, digest, rid, json.dumps(result, ensure_ascii=False, sort_keys=True)))
            row = db.execute("SELECT run_id, result FROM batches WHERE kind=? AND digest=?",
                             (kind, digest)).fetchone()
        return {"run_id": row[0], "result": json.loads(row[1])}

    def lines(self, kind: str, digest: str) -> list[dict]:
        """按批次取回全部原始行，按原文件行号排序。"""
        with self.connect() as db:
            rows = db.execute("SELECT payload FROM batch_lines WHERE kind=? AND digest=? "
                              "ORDER BY source_line", (kind, digest)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def pending(self, kind: str, digest: str) -> list[dict]:
        """按批次取回待核对请求及其原行。"""
        with self.connect() as db:
            rows = db.execute("SELECT payload FROM pending_evidence "
                              "WHERE kind=? AND digest=? ORDER BY rowid", (kind, digest)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def pending_by_request(self, kind: str, digest: str, request_id: str) -> list[dict]:
        """按请求编号查回；同编号多分组时一并返回，绝不只给一条。"""
        with self.connect() as db:
            rows = db.execute("SELECT payload FROM pending_evidence "
                              "WHERE kind=? AND digest=? AND request_id=? ORDER BY rowid",
                              (kind, digest, str(request_id))).fetchall()
        return [json.loads(r[0]) for r in rows]

    def pending_by_key(self, kind: str, digest: str, request_key: str) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT payload FROM pending_evidence "
                              "WHERE kind=? AND digest=? AND request_key=?",
                              (kind, digest, str(request_key))).fetchall()
        return [json.loads(r[0]) for r in rows]

    def count(self) -> int:
        with self.connect() as db:
            return db.execute("SELECT COUNT(*) FROM runs").fetchone()[0]

    def all(self) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT run_id, digest, result FROM runs ORDER BY run_id").fetchall()
        return [{"run_id": r[0], "digest": r[1], "result": json.loads(r[2])} for r in rows]

    def batches(self, kind: str | None = None) -> list[dict]:
        with self.connect() as db:
            if kind:
                rows = db.execute("SELECT kind, run_id, digest, result FROM batches "
                                  "WHERE kind=? ORDER BY rowid", (kind,)).fetchall()
            else:
                rows = db.execute("SELECT kind, run_id, digest, result FROM batches "
                                  "ORDER BY rowid").fetchall()
        return [{"kind": r[0], "run_id": r[1], "digest": r[2], "result": json.loads(r[3])} for r in rows]
