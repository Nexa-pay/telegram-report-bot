import os
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Float, JSON, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import json

# FORCE SQLITE - Ignore any DATABASE_URL from Railway
# This will work immediately
DATABASE_URL = 'sqlite:///bot.db'

# Create engine with SQLite
engine = create_engine(
    DATABASE_URL, 
    connect_args={'check_same_thread': False},  # Needed for SQLite
    echo=True  # This will show SQL queries in logs (optional)
)

Base = declarative_base()
Session = sessionmaker(bind=engine)

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, unique=True)
    username = Column(String, nullable=True)
    tokens = Column(Integer, default=10)
    role = Column(String, default='user')  # 'owner', 'admin', 'user'
    is_active = Column(Boolean, default=True)
    reports_made = Column(Integer, default=0)
    joined_date = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow)

class TelegramAccount(Base):
    __tablename__ = 'telegram_accounts'
    
    id = Column(Integer, primary_key=True)
    phone_number = Column(String, unique=True)
    session_string = Column(Text)  # Changed to Text for longer strings
    is_active = Column(Boolean, default=True)
    added_by = Column(Integer, nullable=True)
    added_date = Column(DateTime, default=datetime.utcnow)
    reports_count = Column(Integer, default=0)
    status = Column(String, default='available')  # 'available', 'busy', 'banned'

class Report(Base):
    __tablename__ = 'reports'
    
    id = Column(Integer, primary_key=True)
    target_type = Column(String)  # 'user', 'group', 'channel'
    target_id = Column(String, nullable=True)
    target_username = Column(String, nullable=True)
    category = Column(String)
    custom_text = Column(Text)  # Changed to Text for longer text
    reported_by = Column(Integer)
    accounts_used = Column(Text, nullable=True)  # JSON string as Text
    status = Column(String, default='pending')  # 'pending', 'completed', 'failed'
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

class Transaction(Base):
    __tablename__ = 'transactions'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    amount = Column(Integer)
    type = Column(String)  # 'purchase', 'reward', 'deduction'
    description = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

# Create tables
def init_db():
    """Initialize database tables"""
    try:
        Base.metadata.create_all(engine)
        print("✅ Database tables created successfully using SQLite!")
        print(f"📁 Database file: bot.db")
        
        # Create a test session to verify
        session = Session()
        session.execute("SELECT 1")
        session.close()
        print("✅ Database connection verified!")
        
    except Exception as e:
        print(f"❌ Error creating database tables: {e}")

# Initialize database on import
init_db()

# Export session factory
def get_session():
    return Session()