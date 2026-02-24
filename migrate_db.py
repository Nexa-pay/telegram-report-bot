#!/usr/bin/env python3
"""Database migration script to update schema to BigInteger"""
import os
import logging
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError
from database import Base, User, TelegramAccount, Report, Transaction
from config import DATABASE_URL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_database():
    """Migrate database to use BigInteger for user IDs"""
    try:
        # Create engine
        if DATABASE_URL.startswith('postgres://'):
            db_url = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
        else:
            db_url = DATABASE_URL
        
        engine = create_engine(db_url)
        
        logger.info("Starting database migration...")
        
        # Drop all tables and recreate
        logger.info("Dropping all tables...")
        Base.metadata.drop_all(engine)
        logger.info("Tables dropped successfully")
        
        # Create all tables with new schema
        logger.info("Creating tables with new schema...")
        Base.metadata.create_all(engine)
        logger.info("✅ Tables created successfully with BigInteger schema")
        
        # Verify
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        logger.info(f"Tables created: {tables}")
        
        # Check user_id column type
        columns = inspector.get_columns('users')
        user_id_col = next((c for c in columns if c['name'] == 'user_id'), None)
        if user_id_col:
            logger.info(f"user_id column type: {user_id_col['type']}")
        
        logger.info("✅ Migration completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        return False

if __name__ == "__main__":
    migrate_database()