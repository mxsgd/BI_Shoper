"""
Skrypt do wypełnienia dim_date (wymiar czasu) dla analiz sezonowości i trendów.
Uruchom: python scripts/seed_dim_date.py
"""
import sys
from datetime import datetime, date, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# Import models
sys.path.insert(0, ".")
from app.models.core.dim_date import DimDate
from app.database import Base

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "user": "postgres",
    "password": "2402",
    "database": "bi_shoper"
}


def generate_dim_date(start_year: int = 2020, end_year: int = 2030):
    """Generuje rekordy dim_date dla zakresu lat."""
    url = f"postgresql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
    
    print(f"🔌 Łączenie z bazą '{DB_CONFIG['database']}'...")
    
    try:
        engine = create_engine(url)
        
        with Session(engine) as session:
            # Sprawdź ile już jest rekordów
            existing_count = session.query(DimDate).count()
            if existing_count > 0:
                print(f"⚠️  Znaleziono {existing_count} istniejących rekordów w dim_date.")
                response = input("Czy nadpisać? (t/n): ").strip().lower()
                if response != 't':
                    print("❌ Anulowano.")
                    return False
                session.query(DimDate).delete()
                session.commit()
            
            print(f"📅 Generowanie dim_date od {start_year} do {end_year}...")
            
            records = []
            current_date = date(start_year, 1, 1)
            end_date = date(end_year, 12, 31)
            
            while current_date <= end_date:
                # Oblicz tydzień (ISO week)
                iso_year, iso_week, iso_weekday = current_date.isocalendar()
                
                # Oblicz kwartał
                quarter = (current_date.month - 1) // 3 + 1
                
                # Czy weekend?
                is_weekend = current_date.weekday() >= 5  # 5=Saturday, 6=Sunday
                
                dim_date = DimDate(
                    date_id=current_date,
                    day=current_date.day,
                    month=current_date.month,
                    year=current_date.year,
                    week=iso_week,
                    quarter=quarter,
                    is_weekend=is_weekend
                )
                records.append(dim_date)
                
                current_date += timedelta(days=1)
                
                # Batch insert co 1000 rekordów
                if len(records) >= 1000:
                    session.bulk_save_objects(records)
                    session.commit()
                    print(f"  ✓ Dodano {len(records)} rekordów (do {current_date - timedelta(days=1)})")
                    records = []
            
            # Dodaj pozostałe
            if records:
                session.bulk_save_objects(records)
                session.commit()
                print(f"  ✓ Dodano {len(records)} rekordów (końcowe)")
            
            total_days = (end_date - date(start_year, 1, 1)).days + 1
            print(f"✅ Utworzono {total_days} rekordów w dim_date ({start_year}-{end_year})")
            return True
            
    except Exception as e:
        print(f"❌ Błąd: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = generate_dim_date(start_year=2020, end_year=2030)
    sys.exit(0 if success else 1)
