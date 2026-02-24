import os
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Text, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from datetime import datetime, timezone  # Fixed: Added timezone import
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get database URL from environment
DATABASE_URL = os.getenv('DATABASE_URL')

if not DATABASE_URL:
    logger.error("❌ CRITICAL: DATABASE_URL not set in environment variables!")
    raise ValueError("DATABASE_URL environment variable is required!")

# Fix for Railway PostgreSQL URL format
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    logger.info("✅ Fixed PostgreSQL URL format")

# Create engine for PostgreSQL
try:
    engine = create_engine(
        DATABASE_URL,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        echo=False
    )
    logger.info("✅ PostgreSQL engine created successfully")
except Exception as e:
    logger.error(f"❌ Failed to create PostgreSQL engine: {e}")
    raise

Base = declarative_base()
Session = sessionmaker(bind=engine)

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String, nullable=True)
    tokens = Column(Integer, default=10)
    role = Column(String, default='user')
    is_active = Column(Boolean, default=True)
    reports_made = Column(Integer, default=0)
    # Fixed: Replaced deprecated utcnow with timezone-aware datetime
    joined_date = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_active = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class TelegramAccount(Base):
    __tablename__ = 'telegram_accounts'
    
    id = Column(Integer, primary_key=True)
    phone_number = Column(String, unique=True, nullable=False)
    session_string = Column(Text)
    is_active = Column(Boolean, default=True)
    added_by = Column(BigInteger, nullable=True)
    added_date = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    reports_count = Column(Integer, default=0)
    status = Column(String, default='available')

class Report(Base):
    __tablename__ = 'reports'
    
    id = Column(Integer, primary_key=True)
    target_type = Column(String)
    target_id = Column(String, nullable=True)
    target_username = Column(String, nullable=True)
    category = Column(String)
    custom_text = Column(Text)
    reported_by = Column(BigInteger, nullable=False)
    accounts_used = Column(Text, nullable=True)
    status = Column(String, default='pending')
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)

class Transaction(Base):
    __tablename__ = 'transactions'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False)
    amount = Column(Integer)
    type = Column(String)
    description = Column(String, nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

def init_db():
    """Initialize database tables"""
    try:
        # Create tables if they don't exist
        Base.metadata.create_all(engine)
        logger.info("✅ Database tables verified/created successfully!")
        
        # Test connection with a simple query
        with engine.connect() as conn:
            # Use text() for raw SQL
            result = conn.execute(text("SELECT 1 as test"))
            # Fetch the result to ensure query executed
            row = result.fetchone()
            if row and row[0] == 1:
                logger.info("✅ Database connection verified!")
            else:
                logger.warning("⚠️ Database connection test returned unexpected result")
            conn.commit()
            
    except Exception as e:
        logger.error(f"❌ Database initialization error: {e}")
        # Don't raise here - allow bot to continue if tables exist
        logger.warning("⚠️ Continuing despite database initialization error...")

# Initialize database
init_db()

def get_session():
    """Get a new database session"""
    return Session()