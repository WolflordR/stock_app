import sqlite3

from modules.data_sources import official_broker_import as broker


def test_broker_list_and_overview_read_latest_imported_day_only(tmp_path, monkeypatch):
    monkeypatch.setattr(broker, "DB_PATH", tmp_path / "broker.db")
    broker.init_official_broker_db()
    with sqlite3.connect(broker.DB_PATH) as conn:
        conn.executemany(
            "INSERT INTO broker_trade_reports VALUES(?,?,?,?,?,?,?,?)",
            [
                ("TWSE", "2026-10-07", "1101", "台泥", "official", "old.csv", "2026-10-07", 1),
                ("TWSE", "2026-10-08", "1101", "台泥", "official", "new.csv", "2026-10-08", 2),
                ("TPEX", "2026-10-09", "1234", "測試", "official", "otc.csv", "2026-10-09", 1),
            ],
        )
        conn.executemany(
            "INSERT INTO broker_trade_lines VALUES(?,?,?,?,?,?,?,?,?,?)",
            [
                ("TWSE", "2026-10-07", "1101", 1, "001", "舊分點", 20, 9000, 0, "{}"),
                ("TWSE", "2026-10-08", "1101", 1, "002", "台北", 21, 1000, 0, "{}"),
                ("TWSE", "2026-10-08", "1101", 2, "003", "高雄", 21, 0, 300, "{}"),
                ("TPEX", "2026-10-09", "1234", 1, "004", "上櫃分點", 30, 2000, 0, "{}"),
            ],
        )

    twse = broker.get_official_broker_db_overview(market="TWSE")
    assert twse["branch_count"] == 2
    assert twse["trade_day_count"] == 2
    assert broker.get_official_broker_db_overview()["branch_count"] == 3

    branches = broker.list_official_broker_branches(market="TWSE")
    assert set(branches["broker_name"]) == {"台北", "高雄"}
    assert branches.set_index("broker_name").loc["台北", "total_net_shares"] == 1000
    assert list(broker.list_official_broker_branches(search_text="上櫃")["broker_name"]) == ["上櫃分點"]
