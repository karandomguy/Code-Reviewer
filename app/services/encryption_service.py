import os
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from typing import Optional
from app.utils.logging import logger
from dotenv import load_dotenv

load_dotenv()

class EncryptionService:
    def __init__(self):
        """Initialize encryption service with key derivation."""
        self._fernet = None
        self._initialize_encryption()
    
    def _initialize_encryption(self):
        """Initialize Fernet encryption with derived key."""
        try:
            # Get encryption key from environment or generate one
            encryption_key = os.getenv('ENCRYPTION_KEY')
            
            if not encryption_key:
                # In production, this should come from secure key management
                logger.warning("ENCRYPTION_KEY not set, using SECRET_KEY for derivation")
                secret_key = os.getenv('SECRET_KEY', 'fallback-key-change-in-production')
                encryption_key = secret_key
            
            # Derive a key using PBKDF2
            password = encryption_key.encode('utf-8')
            salt = b'stable_salt_change_in_production'  # In production, use random salt per user
            
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            
            key = base64.urlsafe_b64encode(kdf.derive(password))
            self._fernet = Fernet(key)
            
        except Exception as e:
            logger.error("Failed to initialize encryption", error=str(e))
            raise Exception("Encryption initialization failed")
    
    def encrypt(self, plaintext: str) -> str:
        """Encrypt a string value."""
        if not plaintext:
            return ""
        
        try:
            encrypted_bytes = self._fernet.encrypt(plaintext.encode('utf-8'))
            return base64.urlsafe_b64encode(encrypted_bytes).decode('utf-8')
        except Exception as e:
            logger.error("Encryption failed", error=str(e))
            raise Exception("Failed to encrypt data")
    
    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a string value."""
        if not ciphertext:
            return ""
        
        try:
            encrypted_bytes = base64.urlsafe_b64decode(ciphertext.encode('utf-8'))
            decrypted_bytes = self._fernet.decrypt(encrypted_bytes)
            return decrypted_bytes.decode('utf-8')
        except Exception as e:
            logger.error("Decryption failed", error=str(e))
            raise Exception("Failed to decrypt data")
    
    def is_encrypted(self, value: str) -> bool:
        """Check if a value appears to be encrypted."""
        try:
            # Encrypted values will be base64 encoded and longer
            if not value or len(value) < 50:
                return False
            
            # Try to decode as base64
            base64.urlsafe_b64decode(value.encode('utf-8'))
            return True
        except Exception:
            return False

# Global instance
encryption_service = EncryptionService()