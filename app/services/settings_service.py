"""Service for managing server settings with encryption."""

import base64
import logging
from typing import Any, Optional

from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from ..config import settings as app_settings
from ..models import ServerSettings

logger = logging.getLogger(__name__)


class SettingsService:
    """Service for managing encrypted server settings."""

    # Settings that should be encrypted
    ENCRYPTED_KEYS = {
        "smtp_password",
        "secret_key",
        "jwt_secret_key",
        "b2_secret_access_key",
    }

    def __init__(self, db: Session):
        """Initialize settings service."""
        self.db = db
        self._cipher = self._get_cipher()

    @staticmethod
    def get_domain(db: Session) -> str:
        """
        Get the domain URL with priority: database settings > config default.

        Args:
            db: Database session

        Returns:
            Domain URL (e.g., "https://alima.example.com")
        """
        try:
            service = SettingsService(db)
            domain = service.get("domain")
            if domain:
                return domain
        except Exception:
            pass

        # Fall back to config default
        return app_settings.domain

    def _get_cipher(self) -> Fernet:
        """Get or create encryption cipher."""
        # Use the secret key from config for encryption
        # Derive a Fernet key from the secret key
        key = app_settings.secret_key.encode()
        # Pad or truncate to 32 bytes, then base64 encode
        key = base64.urlsafe_b64encode(key[:32].ljust(32, b"0"))
        return Fernet(key)

    def get(self, key: str, default: Any = None) -> Optional[str]:
        """
        Get a setting value by key.

        Priority: Database setting > Config file > Provided default

        Args:
            key: Setting key
            default: Default value if not found

        Returns:
            Setting value (decrypted if encrypted) or default
        """
        setting = self.db.query(ServerSettings).filter(ServerSettings.key == key).first()

        if not setting or setting.value is None:
            # Try to get from config file as fallback
            config_value = self._get_config_value(key)
            if config_value is not None:
                return str(config_value)
            return default

        if setting.is_encrypted:
            try:
                return self._decrypt(setting.value)
            except Exception as e:
                logger.error(f"Failed to decrypt setting {key}: {e}")
                # Try config fallback on decryption error
                config_value = self._get_config_value(key)
                if config_value is not None:
                    return str(config_value)
                return default

        return setting.value

    def _get_config_value(self, key: str) -> Optional[Any]:
        """
        Get a value from the config file or provide hardcoded defaults.

        Only domain is read from config - all other settings use hardcoded defaults.

        Args:
            key: Setting key

        Returns:
            Config value or hardcoded default
        """
        # Only domain comes from config
        if key == "domain":
            return app_settings.domain

        # B2 storage falls back to its B2_* environment variables, so an
        # existing .env-based setup keeps working after these became editable
        # in the Server Settings UI.
        if key.startswith("b2_"):
            return getattr(app_settings, key, None)

        # All other settings have hardcoded defaults
        # These are the defaults if not set in Server Settings UI
        defaults = {
            "app_name": "Alima",
            "quick_sync_interval_minutes": 1,
            "full_sync_interval_minutes": 1440,  # 24 hours
            "download_quality": "High",
            "max_concurrent_downloads": 3,
            "session_expire_hours": 168,  # 7 days
            "invite_expire_days": 7,
            "smtp_port": 587,
        }

        return defaults.get(key)

    def set(
        self,
        key: str,
        value: Optional[str],
        category: str = "general",
        description: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> ServerSettings:
        """
        Set a setting value.

        Args:
            key: Setting key
            value: Setting value
            category: Setting category
            description: Setting description
            user_id: ID of user making the change

        Returns:
            Updated or created ServerSettings instance
        """
        setting = self.db.query(ServerSettings).filter(ServerSettings.key == key).first()

        # Determine if this should be encrypted
        should_encrypt = key in self.ENCRYPTED_KEYS

        # Encrypt value if needed
        encrypted_value = self._encrypt(value) if should_encrypt and value else value

        if setting:
            # Update existing
            setting.value = encrypted_value
            setting.is_encrypted = should_encrypt
            setting.category = category
            if description:
                setting.description = description
            if user_id:
                setting.updated_by = user_id
        else:
            # Create new
            setting = ServerSettings(
                key=key,
                value=encrypted_value,
                is_encrypted=should_encrypt,
                category=category,
                description=description,
                updated_by=user_id,
            )
            self.db.add(setting)

        self.db.commit()
        self.db.refresh(setting)
        return setting

    def delete(self, key: str) -> bool:
        """
        Delete a setting.

        Args:
            key: Setting key

        Returns:
            True if deleted, False if not found
        """
        setting = self.db.query(ServerSettings).filter(ServerSettings.key == key).first()

        if setting:
            self.db.delete(setting)
            self.db.commit()
            return True

        return False

    def get_all(self, category: Optional[str] = None) -> dict[str, Any]:
        """
        Get all settings as a dictionary.

        Args:
            category: Optional category filter

        Returns:
            Dictionary of setting key-value pairs (decrypted)
        """
        query = self.db.query(ServerSettings)

        if category:
            query = query.filter(ServerSettings.category == category)

        settings = query.all()
        result = {}

        for setting in settings:
            if setting.value is None:
                result[setting.key] = None
            elif setting.is_encrypted:
                try:
                    result[setting.key] = self._decrypt(setting.value)
                except Exception as e:
                    logger.error(f"Failed to decrypt setting {setting.key}: {e}")
                    result[setting.key] = None
            else:
                result[setting.key] = setting.value

        return result

    def get_all_metadata(self, category: Optional[str] = None) -> list[dict]:
        """
        Get all settings with metadata (but masked values for encrypted settings).

        Args:
            category: Optional category filter

        Returns:
            List of setting dictionaries with metadata
        """
        query = self.db.query(ServerSettings)

        if category:
            query = query.filter(ServerSettings.category == category)

        settings = query.all()
        result = []

        for setting in settings:
            # Mask encrypted values for display
            display_value = setting.value
            if setting.is_encrypted and setting.value:
                display_value = "••••••••"

            result.append({
                "key": setting.key,
                "value": display_value,
                "category": setting.category,
                "description": setting.description,
                "is_encrypted": setting.is_encrypted,
                "updated_at": setting.updated_at,
            })

        return result

    def _encrypt(self, value: str) -> str:
        """Encrypt a value."""
        if not value:
            return value
        return self._cipher.encrypt(value.encode()).decode()

    def _decrypt(self, value: str) -> str:
        """Decrypt a value."""
        if not value:
            return value
        return self._cipher.decrypt(value.encode()).decode()
