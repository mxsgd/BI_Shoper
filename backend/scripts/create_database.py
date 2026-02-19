"""
Skrypt do utworzenia bazy danych bi_shoper w PostgreSQL.
Uruchom: python scripts/create_database.py
"""
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError

# Parametry połączenia (bez nazwy bazy, bo łączymy się do 'postgres')
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "user": "postgres",
    "password": "2402",
    "database": "postgres"  # Łączymy się do domyślnej bazy 'postgres'
}

DB_NAME = "bi_shoper"


def create_database():
    """Tworzy bazę danych jeśli nie istnieje."""
    # URL bez nazwy bazy (łączy się do 'postgres')
    url = f"postgresql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
    
    print(f"🔌 Łączenie z PostgreSQL na {DB_CONFIG['host']}:{DB_CONFIG['port']}...")
    
    try:
        engine = create_engine(url, isolation_level="AUTOCOMMIT")
        
        with engine.connect() as conn:
            # Sprawdź czy baza już istnieje
            result = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :db_name"),
                {"db_name": DB_NAME}
            )
            exists = result.fetchone()
            
            if exists:
                print(f"✅ Baza '{DB_NAME}' już istnieje!")
                return True
            
            # Utwórz bazę
            print(f"📦 Tworzenie bazy '{DB_NAME}'...")
            conn.execute(text(f'CREATE DATABASE "{DB_NAME}"'))
            print(f"✅ Baza '{DB_NAME}' została utworzona!")
            return True
            
    except Exception as e:
        print(f"❌ Błąd: {e}")
        print("\n💡 Sprawdź czy:")
        print("   1. PostgreSQL jest uruchomiony")
        print("   2. Hasło jest poprawne (2402)")
        print("   3. Port jest poprawny (5432)")
        return False


if __name__ == "__main__":
    success = create_database()
    sys.exit(0 if success else 1)
