import os
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Text, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get database URL from environment
DATABASE_URL = os.getenv('DATABASE_URL')

if not DATABASE_URL:
    logger.error("❌ DATABASE_URL not set in environment variables!")
    # Fallback to SQLite (but this will still have readonly issue on Railway)
    DATABASE_URL = 'sqlite:///bot.db'
    logger.warning("⚠️ Using SQLite fallback - may cause readonly errors!")

# Fix for Railway PostgreSQL
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

# Create engine with proper settings
if 'postgresql' in DATABASE_URL:
    # PostgreSQL engine
    engine = create_engine(
        DATABASE_URL,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        echo=False
    )
    logger.info("✅ Using PostgreSQL database")
else:
    # SQLite engine - this will fail on Railway!
    engine = create_engine(
        DATABASE_URL, 
        connect_args={'check_same_thread': False}
    )
    logger.warning("⚠️ Using SQLite - may cause readonly errors on Railway!")

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
    joined_date = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow)

class TelegramAccount(Base):
    __tablename__ = 'telegram_accounts'
    
    id = Column(Integer, primary_key=True)
    phone_number = Column(String, unique=True, nullable=False)
    session_string = Column(Text)
    is_active = Column(Boolean, default=True)
    added_by = Column(BigInteger, nullable=True)
    added_date = Column(DateTime, default=datetime.utcnow)
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
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

class Transaction(Base):
    __tablename__ = 'transactions'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False)
    amount = Column(Integer)
    type = Column(String)
    description = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

# Create tables
def init_db():
    """Initialize database tables"""
    try:
        Base.metadata.create_all(engine)
        logger.info("✅ Database tables verified/created successfully!")
        
        # Test connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            conn.commit()
        logger.info("✅ Database connection verified!")
        
    except Exception as e:
        logger.error(f"❌ Database error: {e}")

init_db()

def get_session():
    return Session()