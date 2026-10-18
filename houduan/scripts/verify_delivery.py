"""Exercise A2 DDL and transaction patterns in a NEW MySQL test database.

Python standard library only. This does not test the unimplemented Flask API.
Password, if needed, is inherited through MYSQL_PWD. Never prints it.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import uuid


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mysql", required=True)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=3306)
    p.add_argument("--user", default="root")
    p.add_argument("--database", required=True)
    p.add_argument("--report", default=None)
    a = p.parse_args()
    if not re.fullmatch(r"a2_verify_[a-zA-Z0-9_]+", a.database):
        p.error("database must start with a2_verify_ and contain only ASCII letters/digits/_")
    root = Path(__file__).resolve().parent.parent / "sql"
    command = [a.mysql, "--no-defaults", "--protocol=TCP", f"--host={a.host}",
               f"--port={a.port}", f"--user={a.user}", "--default-character-set=utf8mb4",
               "--batch", "--skip-column-names", "--raw"]
    results = []

    def sql(text, db=True, error=None):
        r = subprocess.run(command + ([f"--database={a.database}"] if db else []),
                           input="SET time_zone='+08:00';\n" + text,
                           text=True, encoding="utf-8", capture_output=True, timeout=35)
        if error:
            assert r.returncode != 0 and f"ERROR {error} " in r.stderr, (error, r.stderr)
        elif r.returncode:
            raise RuntimeError(r.stderr)
        return r.stdout.strip()

    def check(name, fn):
        fn()
        results.append({"case": name, "result": "PASS"})
        print("PASS", name, flush=True)

    version = sql("SELECT VERSION();", False)
    found = sql("SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name='" + a.database + "';", False)
    if found != "0":
        raise RuntimeError("Refusing to modify an existing database: " + a.database)
    sql((root / "schema.sql").read_text(encoding="utf-8").replace("campus_repair", a.database), False)
    sql((root / "seed.sql").read_text(encoding="utf-8").replace("campus_repair", a.database))

    def expect(actual, wanted):
        assert actual == wanted, (actual, wanted)

    check("DB01 four tables and four seeded users", lambda: expect(sql("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE(); SELECT COUNT(*) FROM `user`;"), "4\n4"))

    def passwords():
        rows = sql("SELECT password FROM `user` ORDER BY id;").splitlines()
        for stored in rows:
            method, salt, digest = stored.split("$")
            _, algorithm, rounds = method.split(":")
            assert hashlib.pbkdf2_hmac(algorithm, b"Demo@123456", salt.encode(), int(rounds)).hex() == digest
        assert len(rows) == 4
    check("DB02 seeded password hashes validate", passwords)
    check("DB03 duplicate username rejected", lambda: sql((root / "seed.sql").read_text(encoding="utf-8").replace("campus_repair", a.database), error=1062))
    check("DB04 role is case sensitive and restricted", lambda: sql("UPDATE `user` SET role='student' WHERE username='stu1';", error=3819))
    ids = dict(line.split("\t") for line in sql("SELECT username,id FROM `user`;").splitlines())
    stu, admin, w1, w2 = [ids[k] for k in ["stu1", "admin", "worker1", "worker2"]]

    def create(token):
        return sql(f"""START TRANSACTION;
INSERT INTO repair_order (order_no,student_id,request_token,request_hash,category,location,description)
VALUES ('{uuid.uuid4().hex}',{stu},'{token}',REPEAT('a',64),'水电','A栋101','漏水');
SET @id=LAST_INSERT_ID();
INSERT INTO order_log (order_id,event_type,to_status,order_version,operator_id)
VALUES (@id,'CREATE','CREATED',0,{stu});
COMMIT; SELECT @id;""")

    oid = create("normal")
    check("DB05 duplicate request token rejected", lambda: sql(f"INSERT INTO repair_order (order_no,student_id,request_token,request_hash,category,location,description) VALUES ('different-number',{stu},'normal',REPEAT('b',64),'水电','A栋101','漏水');", error=1062))
    check("DB06 foreign key rejects missing user", lambda: sql(f"UPDATE repair_order SET student_id=999999999 WHERE id={oid};", error=1452))
    check("DB07 invalid state and missing worker rejected", lambda: (sql(f"UPDATE repair_order SET status='UNKNOWN' WHERE id={oid};", error=3819), sql(f"UPDATE repair_order SET status='ASSIGNED' WHERE id={oid};", error=3819)))
    check("DB08 idempotency token case is preserved", lambda: (create("casekey"), create("Casekey")))

    def change(order, old, new, ver, event, actor, fields="", remark="测试记录"):
        assigned_worker = f"(SELECT worker_id FROM repair_order WHERE id={order})" if event == "ASSIGN" else "NULL"
        sql(f"""START TRANSACTION;
UPDATE repair_order SET status='{new}',version=version+1{fields} WHERE id={order} AND status='{old}' AND version={ver};
SET @changed=ROW_COUNT();
INSERT INTO order_log (order_id,event_type,from_status,to_status,order_version,operator_id,remark,to_worker_id)
SELECT {order},'{event}','{old}','{new}',{ver+1},{actor},'{remark}',{assigned_worker} WHERE @changed=1;
COMMIT;""")

    def lifecycle():
        change(oid, "CREATED", "ASSIGNED", 0, "ASSIGN", admin, f",worker_id={w1},assign_time=NOW()")
        change(oid, "ASSIGNED", "PROCESSING", 1, "ACCEPT", w1, ",accept_time=NOW()")
        change(oid, "PROCESSING", "DONE", 2, "FINISH", w1, ",finish_time=NOW(),repair_record='更换阀芯'")
        change(oid, "DONE", "PROCESSING", 3, "REJECT", stu, ",finish_time=NULL")
        expect(sql(f"SELECT finish_time IS NULL FROM repair_order WHERE id={oid};"), "1")
        change(oid, "PROCESSING", "DONE", 4, "FINISH", w1, ",finish_time=NOW(),repair_record='再次密封'")
        change(oid, "DONE", "CLOSED", 5, "CONFIRM", stu, ",close_time=NOW()")
        expect(sql(f"SELECT status,version FROM repair_order WHERE id={oid}; SELECT COUNT(*) FROM order_log WHERE order_id={oid};"), "CLOSED\t6\n7")
    check("DB09 normal flow including rejection has consistent versions", lifecycle)
    sql(f"INSERT INTO evaluation (order_id,score,content) VALUES ({oid},5,'已修好');")
    check("DB10 duplicate evaluation rejected", lambda: sql(f"INSERT INTO evaluation (order_id,score) VALUES ({oid},4);", error=1062))
    check("DB11 rating out of range rejected", lambda: (sql(f"INSERT INTO evaluation (order_id,score) VALUES ({oid},0);", error=3819), sql(f"INSERT INTO evaluation (order_id,score) VALUES ({oid},6);", error=3819)))
    check("DB12 invalid log transition rejected", lambda: sql(f"INSERT INTO order_log (order_id,event_type,from_status,to_status,order_version,operator_id) VALUES ({oid},'ACCEPT','DONE','PROCESSING',7,{w1});", error=3819))

    rollback_id = create("rollback")
    def rollback():
        sql(f"START TRANSACTION; UPDATE repair_order SET worker_id={w1},status='ASSIGNED',version=1 WHERE id={rollback_id}; INSERT INTO order_log (order_id,event_type,from_status,to_status,order_version,operator_id,to_worker_id) VALUES ({rollback_id},'ASSIGN','CREATED','ASSIGNED',1,999999999,{w1}); COMMIT;", error=1452)
        expect(sql(f"SELECT status,version FROM repair_order WHERE id={rollback_id}; SELECT COUNT(*) FROM order_log WHERE order_id={rollback_id};"), "CREATED\t0\n1")
    check("DB13 log failure rolls back order mutation", rollback)

    race_id = create("race")
    def competitor(worker):
        return sql(f"""START TRANSACTION;
UPDATE repair_order SET worker_id={worker},assign_time=NOW(),status='ASSIGNED',version=1 WHERE id={race_id} AND status='CREATED' AND version=0;
SET @changed=ROW_COUNT(); DO SLEEP(0.4);
INSERT INTO order_log (order_id,event_type,from_status,to_status,order_version,operator_id,to_worker_id)
SELECT {race_id},'ASSIGN','CREATED','ASSIGNED',1,{admin},{worker} WHERE @changed=1;
COMMIT; SELECT @changed;""")
    def race():
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcome = sorted(pool.map(competitor, [w1, w2]))
        expect(outcome, ["0", "1"])
        expect(sql(f"SELECT version FROM repair_order WHERE id={race_id}; SELECT COUNT(*) FROM order_log WHERE order_id={race_id};"), "1\n2")
    check("DB14 concurrent assignment only one succeeds", race)
    check("DB15 stale version cannot overwrite assignment", lambda: expect(sql(f"UPDATE repair_order SET worker_id={w2},version=version+1 WHERE id={race_id} AND status='ASSIGNED' AND version=0; SELECT ROW_COUNT();"), "0"))
    def reassign():
        sql(f"""START TRANSACTION;
SET @oldworker=(SELECT worker_id FROM repair_order WHERE id={race_id});
SET @newworker=IF(@oldworker={w1},{w2},{w1});
UPDATE repair_order SET worker_id=@newworker,assign_time=NOW(),version=version+1 WHERE id={race_id} AND status='ASSIGNED' AND version=1;
INSERT INTO order_log (order_id,event_type,from_status,to_status,order_version,operator_id,from_worker_id,to_worker_id)
VALUES ({race_id},'REASSIGN','ASSIGNED','ASSIGNED',2,{admin},@oldworker,@newworker);
COMMIT;""")
        expect(sql(f"SELECT from_worker_id <> to_worker_id FROM order_log WHERE order_id={race_id} AND event_type='REASSIGN';"), "1")
    check("DB16 reassignment records old and new worker", reassign)
    def overtime():
        sql(f"UPDATE repair_order SET deadline='2000-01-01 00:00:00' WHERE id={race_id};")
        change(race_id, "ASSIGNED", "PROCESSING", 2, "ACCEPT", sql(f"SELECT worker_id FROM repair_order WHERE id={race_id};"), ",accept_time=NOW()")
        actor = sql(f"SELECT worker_id FROM repair_order WHERE id={race_id};")
        change(race_id, "PROCESSING", "DONE", 3, "FINISH", actor, ",finish_time=NOW(),repair_record='完成',is_overtime=(is_overtime=1 OR NOW()>deadline)")
        expect(sql(f"SELECT is_overtime FROM repair_order WHERE id={race_id};"), "1")
    check("DB17 finish marks overdue even before scanner", overtime)

    report = {"mysql_version": version, "database": a.database, "passed": len(results),
              "cases": results, "scope": "DDL, seed hashes and SQL transaction patterns; not Flask/API end-to-end tests"}
    if a.report:
        Path(a.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": len(results), "mysql_version": version}))


if __name__ == "__main__":
    main()
