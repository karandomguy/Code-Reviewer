from sqlalchemy import TypeDecorator, Text
from app.utils.logging import logger

class EncryptedType(TypeDecorator):
    """Custom SQLAlchemy type that automatically encrypts/decrypts values."""
    
    impl = Text
    cache_ok = True
    
    def process_bind_param(self, value, dialect):
        """Encrypt value before storing in database."""
        if value is None:
            return value
        
        if isinstance(value, str) and value:
            try:
                from app.services.encryption_service import encryption_service
                
                if encryption_service.is_encrypted(value):
                    return value
                
                encrypted_value = encryption_service.encrypt(value)
                logger.debug("Encrypted value for database storage")
                return encrypted_value
            except Exception as e:
                logger.error("Failed to encrypt value for database", error=str(e))
                raise
        
        return value
    
    def process_result_value(self, value, dialect):
        """Decrypt value when retrieving from database."""
        if value is None:
            return value
        
        if isinstance(value, str) and value:
            try:
                from app.services.encryption_service import encryption_service
                
                if encryption_service.is_encrypted(value):
                    decrypted_value = encryption_service.decrypt(value)
                    logger.debug("Decrypted value from database")
                    return decrypted_value
                else:
                    logger.warning("Found unencrypted token in database")
                    return value
            except Exception as e:
                logger.error("Failed to decrypt value from database", error=str(e))
                return value
        
        return value