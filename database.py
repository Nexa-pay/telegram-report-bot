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
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///bot.db')

# Fix for Railway PostgreSQL
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

# Create engine with proper settings
if DATABASE_URL.startswith('sqlite'):
    # For SQLite (development)
    engine = create_engine(
        DATABASE_URL, 
        connect_args={'check_same_thread': False}
    )
else:
    # For PostgreSQL (production)
    engine = create_engine(
        DATABASE_URL,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True
    )

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, unique=True, nullable=False)  # Changed to BigInteger with nullable=False
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
        # Check if we need to recreate tables
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        
        if 'users' in tables:
            # Check if user_id column is BigInteger
            columns = inspector.get_columns('users')
            user_id_column = next((col for col in columns if col['name'] == 'user_id'), None)
            
            if user_id_column and str(user_id_column['type']) == 'INTEGER':
                logger.info("Updating database schema to use BigInteger...")
                # Drop and recreate all tables
                Base.metadata.drop_all(engine)
                logger.info("Dropped old tables")
        
        # Create all tables
        Base.metadata.create_all(engine)
        logger.info("✅ Database tables created successfully!")
        
        # Verify connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            conn.commit()
        logger.info("✅ Database connection verified!")
        
    except Exception as e:
        logger.error(f"❌ Error creating database tables: {e}")
        logger.info("⚠️ Attempting to continue with existing database...")

# Import inspect only when needed
from sqlalchemy import inspect

# Initialize database on import
init_db()

def get_session():
    return Session()