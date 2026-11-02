from sqlalchemy import create_engine, text

DATABASE_PATH = "postgresql+psycopg://dofkee:helloworld@localhost:5001/demo?client_encoding=utf8"
engine = create_engine(DATABASE_PATH)

engine = create_engine(DATABASE_PATH)

def run_test_query():
    with engine.connect() as connection:
        query = text("SELECT * FROM Airports LIMIT 20")
        result = connection.execute(query)

        for i in result:
            print(i)


def create_table_bookings_json():
    with engine.connect() as connection:
        # query = ""

run_test_query()