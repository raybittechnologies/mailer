# -*- encoding: utf-8 -*-
"""
Database utility functions for proper connection management
"""

from contextlib import contextmanager
from sqlalchemy.exc import SQLAlchemyError, DisconnectionError
from apps import db
import logging

logger = logging.getLogger(__name__)

@contextmanager
def db_session():
    """
    Context manager for database sessions with proper error handling and cleanup
    """
    session = db.session
    try:
        yield session
        session.commit()
    except SQLAlchemyError as e:
        logger.error(f"Database error: {e}")
        session.rollback()
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        session.rollback()
        raise
    finally:
        # Do not close the shared Flask-SQLAlchemy scoped session here.
        # The extension manages lifecycle per-request; closing here can detach objects.
        pass

@contextmanager
def db_transaction():
    """
    Context manager for database transactions with automatic rollback on error
    """
    session = db.session
    try:
        yield session
        session.commit()
    except Exception as e:
        logger.error(f"Transaction error: {e}")
        session.rollback()
        raise
    finally:
        # Avoid closing the shared session inside request handlers.
        pass

def safe_db_operation(operation, *args, **kwargs):
    """
    Safely execute a database operation with proper error handling
    """
    try:
        return operation(*args, **kwargs)
    except (SQLAlchemyError, DisconnectionError) as e:
        logger.error(f"Database operation failed: {e}")
        db.session.rollback()
        raise
    except Exception as e:
        logger.error(f"Unexpected error in database operation: {e}")
        db.session.rollback()
        raise

def bulk_save_with_retry(objects, batch_size=1000, max_retries=3):
    """
    Perform bulk save operations with retry logic and batching
    """
    if not objects:
        return
    
    session = db.session
    total_objects = len(objects)
    
    try:
        for batch_start in range(0, total_objects, batch_size):
            batch_end = min(batch_start + batch_size, total_objects)
            batch = objects[batch_start:batch_end]
            
            for attempt in range(max_retries):
                try:
                    session.bulk_save_objects(batch)
                    session.commit()
                    logger.info(f"Successfully saved batch {batch_start}-{batch_end} of {total_objects}")
                    break
                except (SQLAlchemyError, DisconnectionError) as e:
                    logger.warning(f"Batch save attempt {attempt + 1} failed: {e}")
                    session.rollback()
                    if attempt == max_retries - 1:
                        logger.error(f"Failed to save batch {batch_start}-{batch_end} after {max_retries} attempts")
                        raise
                    # Wait before retry
                    import time
                    time.sleep(0.1 * (attempt + 1))
                except Exception as e:
                    logger.error(f"Unexpected error in batch save: {e}")
                    session.rollback()
                    raise
    finally:
        # Leave session management to Flask-SQLAlchemy.
        pass

def get_db_connection_info():
    """
    Get current database connection pool information
    """
    try:
        engine = db.engine
        pool = engine.pool
        return {
            'pool_size': pool.size(),
            'checked_in': pool.checkedin(),
            'checked_out': pool.checkedout(),
            'overflow': pool.overflow(),
            'invalid': pool.invalid()
        }
    except Exception as e:
        logger.error(f"Error getting connection info: {e}")
        return None

def cleanup_connections():
    """
    Clean up database connections
    """
    try:
        db.session.close()
        db.engine.dispose()
        logger.info("Database connections cleaned up")
    except Exception as e:
        logger.error(f"Error cleaning up connections: {e}")
