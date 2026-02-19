"""
Skrypt do podglądu bazy danych bi_shoper przez SQL.
Uruchom: python scripts/view_database.py
"""
import sys
from sqlalchemy import create_engine, text, inspect

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "user": "postgres",
    "password": "2402",
    "database": "bi_shoper"
}


def view_database():
    """Wyświetla informacje o bazie danych."""
    url = f"postgresql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
    
    print(f"🔌 Łączenie z bazą '{DB_CONFIG['database']}'...")
    
    try:
        engine = create_engine(url)
        
        with engine.connect() as conn:
            inspector = inspect(engine)
            
            # Lista tabel
            tables = inspector.get_table_names()
            
            if not tables:
                print("📭 Brak tabel w bazie danych.")
                print("💡 Uruchom backend (uvicorn app.main:app --reload) aby utworzyć tabele.")
                return True
            
            print(f"\n📊 Znaleziono {len(tables)} tabel:\n")
            
            for table_name in tables:
                print(f"  📋 {table_name}")
                columns = inspector.get_columns(table_name)
                print(f"     Kolumny: {', '.join([col['name'] for col in columns])}")
                
                # Liczba wierszy
                result = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"'))
                count = result.scalar()
                print(f"     Wierszy: {count}")
                print()
            
            # Przykładowe zapytanie SQL
            print("\n" + "="*60)
            print("💡 Przykładowe zapytania SQL:")
            print("="*60)
            print("\nSELECT * FROM products LIMIT 10;")
            print("SELECT * FROM orders LIMIT 10;")
            print("SELECT * FROM stores;")
            print("\nAby wykonać zapytanie, użyj psql lub pgAdmin.")
            
        return True
        
    except Exception as e:
        print(f"❌ Błąd: {e}")
        print("\n💡 Sprawdź czy:")
        print("   1. Baza 'bi_shoper' istnieje (utwórz w pgAdmin: prawy klik Databases → Create → Database, nazwa: bi_shoper)")
        print("   2. PostgreSQL jest uruchomiony")
        print("   3. Hasło jest poprawne (2402)")
        return False


if __name__ == "__main__":
    success = view_database()
    sys.exit(0 if success else 1)
