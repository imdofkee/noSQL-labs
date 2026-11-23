from sqlalchemy import create_engine, text

DATABASE_PATH = "postgresql+psycopg://dofkee:helloworld@localhost:5001/demo?client_encoding=utf8"
engine = create_engine(DATABASE_PATH)

def reset_bookings_json():
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS bookings_json CASCADE;"))
    print("Ресет БД выполнен")


# создание таблицы
def create_bookings_json_table():
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS bookings_json (
                id         BIGSERIAL     PRIMARY KEY,
                booking_id bpchar(6)     NOT NULL REFERENCES bookings(book_ref),
                data       JSONB         NOT NULL,
                created_at TIMESTAMPTZ   NOT NULL DEFAULT now()
            );
        """))
    print("bookings_json готова")


# заполнение bookings_json
def populate_bookings_json(limit: int = 50000):
    with engine.begin() as conn:
        res = conn.execute(text("""
            INSERT INTO bookings_json (booking_id, data)
            WITH selected AS (
                SELECT b.book_ref
                FROM bookings b
                WHERE NOT EXISTS (
                    SELECT 1 FROM bookings_json bj WHERE bj.booking_id = b.book_ref
                )
                ORDER BY b.book_ref
                LIMIT :limit
            )
            SELECT
                s.book_ref,
                jsonb_build_object(
                    'booking_number', 'BKG-' || s.book_ref,
                    'status',         'confirmed',
                    'passengers',     COALESCE(t.passengers, '[]'::jsonb),
                    'additional_services', '[]'::jsonb,
                    'notes',          NULL
                )
            FROM selected s
            LEFT JOIN (
                SELECT
                    tk.book_ref,
                    jsonb_agg(
                        jsonb_build_object(
                            'id',   tk.passenger_id,
                            'name', tk.passenger_name,
                            'meal', 'standard'
                        )
                        ORDER BY tk.passenger_id
                    ) AS passengers
                FROM (
                    SELECT DISTINCT book_ref, passenger_id, passenger_name
                    FROM tickets
                    WHERE book_ref IN (SELECT book_ref FROM selected)
                ) tk
                GROUP BY tk.book_ref
            ) t ON t.book_ref = s.book_ref;
        """), {"limit": limit})
        print(f"bookings_json заполнена {res.rowcount} строками")


def prepare_indexes():
    with engine.begin() as conn:
        conn.execute(text("CREATE INDEX IF NOT EXISTS bp_ticket_no_idx    ON boarding_passes(ticket_no);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS tickets_book_ref_idx ON tickets(book_ref);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS tickets_pid_idx     ON tickets(passenger_id);"))
        conn.execute(text("ANALYZE bookings_json;"))
        conn.execute(text("ANALYZE bookings;"))
        conn.execute(text("ANALYZE tickets;"))
        conn.execute(text("ANALYZE boarding_passes;"))
    print("индексы")


# задание по варианту 31
def add_seats_batch(last_id: int, batch_size: int):
    sql = """
    WITH batch AS (
        SELECT id FROM bookings_json
        WHERE id > :last_id
        ORDER BY id
        LIMIT :batch_size
    ),
    passenger_seats AS (
        SELECT
            bj.id            AS bookings_json_id,
            p->>'id'         AS passenger_id,
            jsonb_agg(DISTINCT bp.seat_no) AS seats_array
        FROM bookings_json bj
        JOIN batch  ON batch.id = bj.id
        JOIN LATERAL jsonb_array_elements(bj.data->'passengers') p ON TRUE
        JOIN bookings b ON b.book_ref     = bj.booking_id
        JOIN tickets  t ON t.book_ref     = b.book_ref
                       AND t.passenger_id = p->>'id'
        JOIN boarding_passes bp ON bp.ticket_no = t.ticket_no
        GROUP BY bj.id, p->>'id'
    )
    UPDATE bookings_json bj
    SET data = CASE
        WHEN jsonb_array_length(bj.data->'passengers') = 0 THEN bj.data
        ELSE jsonb_set(
            bj.data,
            '{passengers}',
            (
                SELECT jsonb_agg(
                           jsonb_set(
                               p,
                               '{seats}',
                               COALESCE(ps.seats_array, '[]'::jsonb)
                           )
                           ORDER BY ord
                       )
                FROM jsonb_array_elements(bj.data->'passengers')
                     WITH ORDINALITY AS el(p, ord)
                LEFT JOIN passenger_seats ps
                       ON ps.bookings_json_id = bj.id
                      AND ps.passenger_id     = p->>'id'
            )
        )
    END
    FROM batch
    WHERE bj.id = batch.id
    RETURNING bj.id;
    """
    with engine.begin() as conn:
        rows = conn.execute(
            text(sql),
            {"last_id": last_id, "batch_size": batch_size},
        ).fetchall()
        if not rows:
            return None
        return max(r[0] for r in rows)


# батчи
def add_seats_all(batch_size: int = 2000):
    last_id  = 0
    batches  = 0
    while True:
        new_last = add_seats_batch(last_id, batch_size)
        if new_last is None:
            break
        batches += 1
        last_id  = new_last
        print(f"batch #{batches} done, last_id={last_id}")
    print(f"Готово. Обработано батчей: {batches}.")


# проверка и вывод
def check_seats():
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT booking_id, jsonb_pretty(data->'passengers')
            FROM bookings_json
            WHERE data->'passengers'->0 ? 'seats'
              AND data->'passengers'->0->'seats' <> '[]'::jsonb
            LIMIT 3
        """)).all()
        if not rows:
            print("No rows with non-empty seats found.")
            return
        for r in rows:
            print(r[0])
            print(r[1])
            print("-" * 60)

create_bookings_json_table()
populate_bookings_json(limit=5000)
prepare_indexes()
add_seats_all(batch_size=2000)
check_seats()