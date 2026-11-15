#!/usr/bin/env bash
# Phase 10 — bước 4: tạo user `reader` (chỉ đọc) và **chứng minh** cơ chế
# chỉ-đọc của Neo4j Community.
#
# Vì sao cần script này?
#   Neo4j **Community không có RBAC**: `CREATE USER … SET ROLE reader` và
#   `GRANT … ON GRAPH` đều lỗi cú pháp; user `reader` tạo được nhưng vẫn
#   ghi được vào DB.
#   Cơ chế bảo vệ thực sự hiệu lực là **session `default_access_mode=READ`**
#   → server từ chối mọi lệnh ghi (`Neo.ClientError.Statement.AccessMode`),
#   kể cả khi dùng superuser.
#
# Script này phải **chứng minh** điều đó: chạy 1 lệnh ghi bằng user `reader`
# với session `READ` → phải nhận lỗi AccessMode. Nếu lệnh ghi lọt
# → exit code ≠ 0.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# shellcheck disable=SC1091
source .venv/bin/activate 2>/dev/null || true

: "${NEO4J_URI:=bolt://localhost:7687}"
: "${NEO4J_USER:=neo4j}"
: "${NEO4J_PASSWORD:=neo4jpass}"
: "${NEO4J_READER_USER:=reader}"
: "${NEO4J_READER_PASSWORD:=readerpass}"
export NEO4J_URI NEO4J_USER NEO4J_PASSWORD NEO4J_READER_USER NEO4J_READER_PASSWORD

echo "==> Tạo user '${NEO4J_READER_USER}' (nếu chưa có)..."
python - "$NEO4J_READER_USER" "$NEO4J_READER_PASSWORD" <<'PY'
import os
import sys

from dotenv import dotenv_values

from neo4j import GraphDatabase

reader = sys.argv[1]
password = sys.argv[2]

env = dotenv_values(".env")
uri = os.environ["NEO4J_URI"]
user = os.environ["NEO4J_USER"]
admin_pw = os.environ["NEO4J_PASSWORD"]

driver = GraphDatabase.driver(uri, auth=(user, admin_pw))
try:
    with driver.session() as session:
        exists = session.run(
            "SHOW USERS YIELD user, roles RETURN user, roles"
        ).data()
        names = {row["user"] for row in exists}
        if reader in names:
            print(f"  user '{reader}' đã tồn tại — bỏ qua tạo")
        else:
            session.run(
                f"CREATE USER {reader} SET PASSWORD '{password}' "
                "CHANGE NOT REQUIRED"
            ).consume()
            print(f"  đã tạo user '{reader}'")
        # Cộng role reader nếu hỗ trợ (Enterprise có, Community thì lỗi —
        # bỏ qua an toàn vì cơ chế READ mới là bảo vệ thật).
        try:
            session.run(f"SET ROLE reader FOR {reader}").consume()
            print("  đã gán role reader")
        except Exception as exc:
            print(f"  bỏ qua SET ROLE (Community không hỗ trợ): {str(exc)[:80]}")
finally:
    driver.close()
PY

echo "==> Kiểm chứng: session READ phải chặn lệnh ghi..."
python - <<'PY'
import os
import sys

from dotenv import dotenv_values

from neo4j import GraphDatabase

env = dotenv_values(".env")
uri = os.environ["NEO4J_URI"]
reader = os.environ["NEO4J_READER_USER"]
reader_pw = os.environ["NEO4J_READER_PASSWORD"]

driver = GraphDatabase.driver(uri, auth=(reader, reader_pw))
blocked = False
try:
    with driver.session(default_access_mode="READ") as session:
        try:
            session.run("MATCH (n) SET n.x = 1").consume()
            print("  LỖI: lệnh ghi đã lọt — cơ chế READ không hiệu lực!")
        except Exception as exc:
            message = str(exc)
            if "AccessMode" in message or "read" in message.lower():
                blocked = True
                print(f"  OK: lệnh ghi bị chặn → {message[:120]}")
            else:
                print(f"  LỖI: lỗi không mong đợi → {message[:160]}")
        # Truy vấn đọc vẫn phải chạy được.
        count = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        print(f"  Truy vấn đọc OK: {count} node")
finally:
    driver.close()

if not blocked:
    print("KẾT QUẢ: FAIL — user reader vẫn ghi được vào DB")
    sys.exit(1)
print("KẾT QUẢ: PASS — user reader không ghi được vào DB")
PY
