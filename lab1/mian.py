from sqlalchemy import create_engine, text

# PATH_TO_DB = "C:/Users/User/Documents/DB/demo-20250901-3m.sql"

DATABASE_PATH = "postgresql+psycopg://dofkee:helloworld@localhost:5001/demo_db?client_encoding=utf8"
engine = create_engine(DATABASE_PATH)

engine = create_engine(DATABASE_PATH)

def run_test_query():
    with engine.connect() as connection:
        query = text("SELECT * FROM airports LIMIT 5")
        result = connection.execute(query)

        for i in result:
            print(i)

run_test_query()