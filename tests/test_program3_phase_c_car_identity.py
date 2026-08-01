"""Program 3 Phase C6 — resolve car name from the GT7 packet car id, not cars.id.

`car_id` app-wide is the GT7 packet id; the old `SELECT name FROM cars WHERE id=?`
matched the surrogate PK by coincidence. The name is now mapped via a recorded
session (sessions.car_id IS the packet id).
"""

from data.session_db import SessionDB


def test_car_name_resolved_from_session_packet_id(tmp_path):
    db = SessionDB(str(tmp_path / "s.db"))
    # a recorded session for GT7 packet car id 333
    db.open_session(333, "Fuji", "Practice", car_name="Porsche 911 RSR '17")
    assert db._car_name_for_packet_id(333) == "Porsche 911 RSR '17"


def test_unknown_and_zero_packet_id(tmp_path):
    db = SessionDB(str(tmp_path / "s.db"))
    assert db._car_name_for_packet_id(0) == ""
    assert db._car_name_for_packet_id(999) == ""   # no session, no cars row


def test_session_mapping_wins_over_coincidental_cars_id(tmp_path):
    """A cars.id surrogate that happens to equal a packet id must NOT be used when a
    real session mapping exists."""
    db = SessionDB(str(tmp_path / "s.db"))
    # cars surrogate row id=1 named 'Surrogate' (autoincrement) ...
    db._conn.execute("INSERT INTO cars(name) VALUES('Surrogate Car')")
    db._conn.commit()
    surrogate_id = db._conn.execute("SELECT id FROM cars WHERE name='Surrogate Car'").fetchone()[0]
    # ... and a session where THAT same integer is the GT7 packet id for a different car
    db.open_session(surrogate_id, "Fuji", "Practice", car_name="Real Packet Car")
    assert db._car_name_for_packet_id(surrogate_id) == "Real Packet Car"
