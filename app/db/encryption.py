"""
Database Encryption Utilities - AES-256 encryption for sensitive trading data
Handles encryption/decryption of broker credentials, API keys, and sensitive information
Compatible with PostgreSQL and supports JSON field encryption
"""

import os
import json
import base64
import logging
from typing import Any, Dict, Optional, Union
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
from app.config import settings

logger = logging.getLogger("encryption")

class DatabaseEncryption:
    """
    AES-256 encryption handler for sensitive database fields
    Encrypts broker credentials, API keys, and other sensitive trading data
    """
    
    def __init__(self, encryption_key: Optional[str] = None):
        """
        Initialize encryption with key from settings or provided key
        """
        self.encryption_key = encryption_key or settings.ENCRYPTION_KEY
        
        if not self.encryption_key:
            raise ValueError("Encryption key not provided in settings or constructor")
        
        # Initialize Fernet cipher
        try:
            # If key is base64 encoded, use directly
            if isinstance(self.encryption_key, str):
                key_bytes = self.encryption_key.encode() if len(self.encryption_key) == 44 else base64.urlsafe_b64encode(self.encryption_key.encode()[:32].ljust(32, b'0'))
            else:
                key_bytes = self.encryption_key
                
            self.cipher = Fernet(key_bytes)
            logger.info("Database encryption initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize encryption: {e}")
            raise
    
    def encrypt_string(self, plaintext: str) -> str:
        """
        Encrypt a string value
        
        Args:
            plaintext: String to encrypt
            
        Returns:
            Base64 encoded encrypted string
        """
        if not plaintext:
            return plaintext
            
        try:
            # Convert to bytes if string
            if isinstance(plaintext, str):
                plaintext_bytes = plaintext.encode('utf-8')
            else:
                plaintext_bytes = plaintext
            
            # Encrypt and encode
            encrypted_bytes = self.cipher.encrypt(plaintext_bytes)
            encrypted_string = base64.urlsafe_b64encode(encrypted_bytes).decode('utf-8')
            
            logger.debug("String encrypted successfully")
            return encrypted_string
            
        except Exception as e:
            logger.error(f"String encryption failed: {e}")
            raise
    
    def decrypt_string(self, encrypted_string: str) -> str:
        """
        Decrypt a string value
        
        Args:
            encrypted_string: Base64 encoded encrypted string
            
        Returns:
            Decrypted plaintext string
        """
        if not encrypted_string:
            return encrypted_string
            
        try:
            # Decode and decrypt
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_string.encode('utf-8'))
            decrypted_bytes = self.cipher.decrypt(encrypted_bytes)
            decrypted_string = decrypted_bytes.decode('utf-8')
            
            logger.debug("String decrypted successfully")
            return decrypted_string
            
        except Exception as e:
            logger.error(f"String decryption failed: {e}")
            raise
    
    def encrypt_json(self, data: Dict[str, Any]) -> str:
        """
        Encrypt a JSON object
        
        Args:
            data: Dictionary to encrypt
            
        Returns:
            Base64 encoded encrypted JSON string
        """
        if not data:
            return json.dumps(data) if data is not None else None
            
        try:
            # Convert to JSON string
            json_string = json.dumps(data, sort_keys=True, separators=(',', ':'))
            
            # Encrypt the JSON string
            encrypted_json = self.encrypt_string(json_string)
            
            logger.debug("JSON data encrypted successfully")
            return encrypted_json
            
        except Exception as e:
            logger.error(f"JSON encryption failed: {e}")
            raise
    
    def decrypt_json(self, encrypted_json: str) -> Dict[str, Any]:
        """
        Decrypt a JSON object
        
        Args:
            encrypted_json: Base64 encoded encrypted JSON string
            
        Returns:
            Decrypted dictionary
        """
        if not encrypted_json:
            return {}
            
        try:
            # Decrypt the JSON string
            json_string = self.decrypt_string(encrypted_json)
            
            # Parse JSON
            data = json.loads(json_string)
            
            logger.debug("JSON data decrypted successfully")
            return data
            
        except Exception as e:
            logger.error(f"JSON decryption failed: {e}")
            raise
    
    def encrypt_broker_credentials(self, credentials: Dict[str, Any]) -> str:
        """
        Encrypt broker credentials with additional validation
        
        Args:
            credentials: Broker credentials dictionary
            
        Returns:
            Encrypted credentials string
        """
        try:
            # Validate required fields
            required_fields = ['api_key', 'api_secret']
            for field in required_fields:
                if field not in credentials:
                    logger.warning(f"Missing required credential field: {field}")
            
            # Add encryption metadata
            credentials_with_metadata = {
                'data': credentials,
                'encrypted_at': datetime.now().isoformat(),
                'version': '1.0'
            }
            
            encrypted_creds = self.encrypt_json(credentials_with_metadata)
            logger.info("Broker credentials encrypted successfully")
            return encrypted_creds
            
        except Exception as e:
            logger.error(f"Broker credentials encryption failed: {e}")
            raise
    
    def decrypt_broker_credentials(self, encrypted_credentials: str) -> Dict[str, Any]:
        """
        Decrypt broker credentials with validation
        
        Args:
            encrypted_credentials: Encrypted credentials string
            
        Returns:
            Decrypted credentials dictionary
        """
        try:
            # Decrypt with metadata
            credentials_with_metadata = self.decrypt_json(encrypted_credentials)
            
            # Extract actual credentials
            credentials = credentials_with_metadata.get('data', {})
            
            # Log decryption (without sensitive data)
            logger.info("Broker credentials decrypted successfully")
            return credentials
            
        except Exception as e:
            logger.error(f"Broker credentials decryption failed: {e}")
            raise
    
    def encrypt_trading_config(self, config: Dict[str, Any]) -> str:
        """
        Encrypt trading configuration settings
        
        Args:
            config: Trading configuration dictionary
            
        Returns:
            Encrypted configuration string
        """
        try:
            # Sensitive config fields to encrypt
            sensitive_fields = [
                'risk_limits', 'position_sizes', 'strategy_params',
                'notification_settings', 'margin_settings'
            ]
            
            # Separate sensitive and non-sensitive data
            sensitive_data = {}
            non_sensitive_data = {}
            
            for key, value in config.items():
                if key in sensitive_fields:
                    sensitive_data[key] = value
                else:
                    non_sensitive_data[key] = value
            
            # Encrypt only sensitive data
            if sensitive_data:
                encrypted_sensitive = self.encrypt_json(sensitive_data)
                non_sensitive_data['encrypted_data'] = encrypted_sensitive
            
            # Return as JSON (non-sensitive + encrypted sensitive)
            return json.dumps(non_sensitive_data)
            
        except Exception as e:
            logger.error(f"Trading config encryption failed: {e}")
            raise
    
    def decrypt_trading_config(self, encrypted_config: str) -> Dict[str, Any]:
        """
        Decrypt trading configuration settings
        
        Args:
            encrypted_config: Encrypted configuration string
            
        Returns:
            Decrypted configuration dictionary
        """
        try:
            # Parse the configuration
            config_data = json.loads(encrypted_config)
            
            # Extract encrypted sensitive data
            encrypted_sensitive = config_data.pop('encrypted_data', None)
            
            # Decrypt sensitive data if present
            if encrypted_sensitive:
                sensitive_data = self.decrypt_json(encrypted_sensitive)
                config_data.update(sensitive_data)
            
            logger.info("Trading config decrypted successfully")
            return config_data
            
        except Exception as e:
            logger.error(f"Trading config decryption failed: {e}")
            raise

# Utility functions for field-level encryption
def encrypt_field(field_value: Union[str, Dict[str, Any]], 
                 encryption_key: Optional[str] = None) -> str:
    """
    Encrypt a single database field
    
    Args:
        field_value: Value to encrypt (string or dict)
        encryption_key: Optional encryption key (uses settings if not provided)
        
    Returns:
        Encrypted field value
    """
    encryptor = DatabaseEncryption(encryption_key)
    
    if isinstance(field_value, dict):
        return encryptor.encrypt_json(field_value)
    else:
        return encryptor.encrypt_string(str(field_value))

def decrypt_field(encrypted_value: str, 
                 return_type: str = 'string',
                 encryption_key: Optional[str] = None) -> Union[str, Dict[str, Any]]:
    """
    Decrypt a single database field
    
    Args:
        encrypted_value: Encrypted field value
        return_type: 'string' or 'json'
        encryption_key: Optional encryption key (uses settings if not provided)
        
    Returns:
        Decrypted field value
    """
    encryptor = DatabaseEncryption(encryption_key)
    
    if return_type == 'json':
        return encryptor.decrypt_json(encrypted_value)
    else:
        return encryptor.decrypt_string(encrypted_value)

# SQLAlchemy custom field types for automatic encryption
from sqlalchemy import TypeDecorator, String, Text
from sqlalchemy.dialects.postgresql import JSON

class EncryptedString(TypeDecorator):
    """
    SQLAlchemy field type that automatically encrypts/decrypts string fields
    """
    impl = Text
    cache_ok = True
    
    def __init__(self, encryption_key: Optional[str] = None, *args, **kwargs):
        self.encryption_key = encryption_key
        super().__init__(*args, **kwargs)
    
    def process_bind_param(self, value, dialect):
        """Encrypt value before storing in database"""
        if value is not None:
            return encrypt_field(value, self.encryption_key)
        return value
    
    def process_result_value(self, value, dialect):
        """Decrypt value after retrieving from database"""
        if value is not None:
            return decrypt_field(value, 'string', self.encryption_key)
        return value

class EncryptedJSON(TypeDecorator):
    """
    SQLAlchemy field type that automatically encrypts/decrypts JSON fields
    """
    impl = Text
    cache_ok = True
    
    def __init__(self, encryption_key: Optional[str] = None, *args, **kwargs):
        self.encryption_key = encryption_key
        super().__init__(*args, **kwargs)
    
    def process_bind_param(self, value, dialect):
        """Encrypt JSON value before storing in database"""
        if value is not None:
            return encrypt_field(value, self.encryption_key)
        return value
    
    def process_result_value(self, value, dialect):
        """Decrypt JSON value after retrieving from database"""
        if value is not None:
            return decrypt_field(value, 'json', self.encryption_key)
        return value

# Key management utilities
def generate_encryption_key() -> str:
    """
    Generate a new Fernet encryption key
    
    Returns:
        Base64 encoded encryption key
    """
    key = Fernet.generate_key()
    return key.decode('utf-8')

def derive_key_from_password(password: str, salt: bytes = None) -> str:
    """
    Derive encryption key from password using PBKDF2
    
    Args:
        password: Password to derive key from
        salt: Salt bytes (generates random if not provided)
        
    Returns:
        Base64 encoded derived key
    """
    if salt is None:
        salt = os.urandom(16)
    
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
        backend=default_backend()
    )
    
    key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
    return key.decode('utf-8')

def validate_encryption_key(key: str) -> bool:
    """
    Validate that encryption key is properly formatted
    
    Args:
        key: Encryption key to validate
        
    Returns:
        True if valid, False otherwise
    """
    try:
        # Try to create Fernet instance
        Fernet(key.encode() if isinstance(key, str) else key)
        return True
    except Exception:
        return False

# Testing utilities
def test_encryption_roundtrip() -> bool:
    """
    Test encryption/decryption roundtrip
    
    Returns:
        True if test passes, False otherwise
    """
    try:
        encryptor = DatabaseEncryption()
        
        # Test string encryption
        test_string = "Test API Key 12345"
        encrypted = encryptor.encrypt_string(test_string)
        decrypted = encryptor.decrypt_string(encrypted)
        
        if test_string != decrypted:
            logger.error("String encryption roundtrip failed")
            return False
        
        # Test JSON encryption
        test_json = {
            "api_key": "test_key_123",
            "api_secret": "test_secret_456",
            "broker": "zerodha"
        }
        encrypted_json = encryptor.encrypt_json(test_json)
        decrypted_json = encryptor.decrypt_json(encrypted_json)
        
        if test_json != decrypted_json:
            logger.error("JSON encryption roundtrip failed")
            return False
        
        logger.info("Encryption roundtrip test passed")
        return True
        
    except Exception as e:
        logger.error(f"Encryption test failed: {e}")
        return False

# Global encryptor instance
try:
    db_encryptor = DatabaseEncryption()
except Exception as e:
    logger.warning(f"Could not initialize global encryptor: {e}")
    db_encryptor = None

# Export main components
__all__ = [
    'DatabaseEncryption',
    'EncryptedString',
    'EncryptedJSON', 
    'encrypt_field',
    'decrypt_field',
    'generate_encryption_key',
    'derive_key_from_password',
    'validate_encryption_key',
    'test_encryption_roundtrip',
    'db_encryptor'
]
