import os
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Text, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy import text
from datetime import datetime, timezone
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get database URL from environment
DATABASE_URL = os.getenv('DATABASE_URL')

if not DATABASE_URL:
    logger.error("❌ CRITICAL: DATABASE_URL not set in environment variables!")
    logger.info("⚠️ Falling back to SQLite for testing...")
    DATABASE_URL = 'sqlite:///bot.db'

# Fix for Railway PostgreSQL URL format
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    logger.info("✅ Fixed PostgreSQL URL format")

# Create engine with proper settings
try:
    if DATABASE_URL.startswith('sqlite'):
        # SQLite for testing
        engine = create_engine(
            DATABASE_URL,
            connect_args={'check_same_thread': False}
        )
        logger.info("✅ SQLite engine created successfully")
    else:
        # PostgreSQL for production
        engine = create_engine(
            DATABASE_URL,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=3600,  # Recycle connections after 1 hour
            echo=False
        )
        logger.info("✅ PostgreSQL engine created successfully")
except Exception as e:
    logger.error(f"❌ Failed to create database engine: {e}")
    raise

# Use scoped session for thread safety
session_factory = sessionmaker(bind=engine)
Session = scoped_session(session_factory)

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String, nullable=True)
    tokens = Column(Integer, default=10)
    role = Column(String, default='user')
    is_active = Column(Boolean, default=True)
    reports_made = Column(Integer, default=0)
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
    last_used = Column(DateTime, nullable=True)

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
    error_message = Column(Text, nullable=True)
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
        
        # Test connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            conn.commit()
            logger.info("✅ Database connection verified!")
            
    except Exception as e:
        logger.error(f"❌ Database initialization error: {e}")
        # Don't raise - allow bot to continue if tables exist

# Initialize database
init_db()

def get_session():
    """Get a new database session"""
    return Session()

def close_session():
    """Close the current session"""
    Session.remove()