from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Float, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import json
from config import DATABASE_URL

engine = create_engine(DATABASE_URL)
Base = declarative_base()
Session = sessionmaker(bind=engine)

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, unique=True)
    username = Column(String)
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
    session_string = Column(String)
    is_active = Column(Boolean, default=True)
    added_by = Column(Integer)
    added_date = Column(DateTime, default=datetime.utcnow)
    reports_count = Column(Integer, default=0)
    status = Column(String, default='available')  # 'available', 'busy', 'banned'

class Report(Base):
    __tablename__ = 'reports'
    
    id = Column(Integer, primary_key=True)
    target_type = Column(String)  # 'user', 'group', 'channel'
    target_id = Column(String)
    target_username = Column(String)
    category = Column(String)
    custom_text = Column(String)
    reported_by = Column(Integer)
    accounts_used = Column(String)  # JSON string
    status = Column(String, default='pending')  # 'pending', 'completed', 'failed'
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)

class Transaction(Base):
    __tablename__ = 'transactions'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    amount = Column(Integer)
    type = Column(String)  # 'purchase', 'reward', 'deduction'
    description = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(engine)