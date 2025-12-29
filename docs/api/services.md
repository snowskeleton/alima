# Services

Auto-generated documentation for Alima's service layer.

## Overview

Services contain the business logic for Alima. They handle operations like email sending, Audible API integration, and settings management.

## EmailService

::: app.services.email_service.EmailService
    options:
      show_source: false
      heading_level: 3
      members:
        - __init__
        - send_invite_email
        - send_test_email
        - send_password_reset_email

Handles email sending via SMTP for:

- Invitation emails
- Test emails
- Password reset emails (future)

Settings are loaded from the database first, with fallback to environment configuration.

## SettingsService

::: app.services.settings_service.SettingsService
    options:
      show_source: false
      heading_level: 3
      members:
        - __init__
        - get
        - set
        - delete
        - get_all

Manages server settings with automatic encryption for sensitive values.

### Encrypted Keys

The following keys are automatically encrypted in the database:

- `smtp_password`
- `secret_key`
- `jwt_secret_key`

Encryption uses Fernet (AES-128) with the application's secret key.

## AudibleService

::: app.services.audible_service.AudibleService
    options:
      show_source: false
      heading_level: 3
      members:
        - __init__
        - authenticate
        - get_library
        - sync_library
        - download_book

Integrates with the Audible API for:

- Authentication
- Library syncing
- Book downloads
- Metadata retrieval

## SnowcryptService

::: app.services.snowcrypt_service.SnowcryptService
    options:
      show_source: false
      heading_level: 3

Handles encryption and decryption of Audible authentication files using the Snowcrypt library.
