# Testing

Guide to running and writing tests for Alima.

## Running Tests

### All Tests

```bash
source .venv/bin/activate
pytest
```

### Verbose Output

```bash
pytest -v
```

### Specific Test File

```bash
pytest tests/test_auth.py
```

### Specific Test Function

```bash
pytest tests/test_auth.py::test_login
```

### Pattern Matching

```bash
pytest -k "auth"      # Run tests with "auth" in name
pytest -k "not slow"  # Skip slow tests
```

### Coverage Report

```bash
pytest --cov=app --cov-report=html
open htmlcov/index.html
```

## Test Structure

Tests are organized by feature:

```
tests/
├── conftest.py           # Shared fixtures
├── test_auth.py         # Authentication tests
├── test_admin.py        # Admin functionality
├── test_accounts.py     # Audible accounts
├── test_library.py      # Library features
├── test_books.py        # Book operations
├── test_feeds.py        # RSS feeds
└── test_settings.py     # Server settings
```

## Test Database

Tests use an isolated in-memory SQLite database:

```python
# conftest.py
@pytest.fixture
def db():
    """Create test database."""
    # Create engine with in-memory database
    engine = create_engine("sqlite:///:memory:")

    # Create tables
    Base.metadata.create_all(engine)

    # Create session
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    yield session

    # Cleanup
    session.close()
```

## Email Mocking

**CRITICAL**: Tests never send real emails. All email functionality is mocked to prevent:

- Sending emails to invalid addresses
- Hurting your domain reputation
- Triggering spam filters
- Costs from email services

The `conftest.py` automatically mocks all email methods:

```python
@pytest.fixture(scope="function")
def mock_email_service():
    """Mock EmailService to prevent sending real emails during tests."""
    with patch("app.services.email_service.EmailService.send_invite_email", ...):
        # All email methods return True (success) without sending
        yield mock_service
```

Additionally, SMTP settings are cleared in test environment:

```python
os.environ["SMTP_HOST"] = ""
os.environ["SMTP_USER"] = ""
os.environ["SMTP_PASSWORD"] = ""
```

### Verifying Email Mocking

```python
def test_invite_email_mocked(admin_client, mock_email_service):
    """Test that invite emails are mocked."""
    # Send invite
    response = admin_client.post("/admin/invites/send", ...)

    # Verify mock was called (but no real email sent)
    mock_email_service["send_invite_email"].assert_called_once()
```

## Writing Tests

### Basic Test

```python
def test_example():
    """Test description."""
    result = my_function()
    assert result == expected
```

### Async Test

```python
@pytest.mark.asyncio
async def test_async_example():
    """Test async function."""
    result = await my_async_function()
    assert result == expected
```

### Using Fixtures

```python
def test_with_database(db):
    """Test using database fixture."""
    user = User(email="test@example.com")
    db.add(user)
    db.commit()

    assert user.id is not None
```

### Testing Routes

```python
def test_route_example(client):
    """Test API endpoint."""
    response = client.get("/some-endpoint")

    assert response.status_code == 200
    assert "expected" in response.text
```

### Testing with Authentication

```python
def test_protected_route(client, test_user, test_session):
    """Test authenticated endpoint."""
    # Include session cookie
    response = client.get(
        "/protected",
        cookies={"session_token": test_session.token}
    )

    assert response.status_code == 200
```

## Common Fixtures

### Database Session

```python
@pytest.fixture
def db():
    """Provides test database session."""
    # Setup
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    yield session

    # Teardown
    session.close()
```

### Test Client

```python
@pytest.fixture
def client(db):
    """Provides FastAPI test client."""
    app.dependency_overrides[get_db] = lambda: db

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
```

### Test User

```python
@pytest.fixture
def test_user(db):
    """Create test user."""
    user = User(
        email="test@example.com",
        password_hash=hash_password("password123"),
        role=UserRole.USER
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
```

### Admin User

```python
@pytest.fixture
def admin_user(db):
    """Create admin user."""
    user = User(
        email="admin@example.com",
        password_hash=hash_password("admin123"),
        role=UserRole.ADMIN
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
```

## Test Categories

### Unit Tests

Test individual functions in isolation:

```python
def test_hash_password():
    """Test password hashing."""
    hashed = hash_password("test123")
    assert hashed != "test123"
    assert verify_password("test123", hashed)
```

### Integration Tests

Test multiple components together:

```python
def test_user_registration_flow(client, db):
    """Test complete registration flow."""
    # Create invite
    response = client.post("/admin/invites/send", ...)

    # Accept invite
    response = client.get(f"/auth/accept-invite?token={token}")

    # Register
    response = client.post("/auth/register", ...)

    # Verify user created
    user = db.query(User).filter_by(email=email).first()
    assert user is not None
```

### End-to-End Tests

Test complete user workflows:

```python
@pytest.mark.e2e
def test_complete_audiobook_flow(client, admin_user):
    """Test from login to downloading a book."""
    # Login
    # Add Audible account
    # Sync library
    # Download book
    # Create feed
    # Access RSS
```

## Mocking

### Mocking External APIs

```python
from unittest.mock import patch, MagicMock

@patch('app.services.audible_service.audible.Client')
def test_audible_sync(mock_client, db):
    """Test syncing with mocked Audible API."""
    mock_instance = MagicMock()
    mock_client.return_value = mock_instance
    mock_instance.get_library.return_value = [...]

    service = AudibleService(db)
    result = service.sync_library()

    assert result is True
```

### Mocking File Operations

```python
@patch('app.services.file_service.Path.exists')
def test_file_check(mock_exists):
    """Test file existence check."""
    mock_exists.return_value = True

    result = check_file()
    assert result is True
```

## Best Practices

### Test Naming

- Use descriptive names
- Follow pattern: `test_<what>_<condition>`
- Examples:
  - `test_login_with_valid_credentials`
  - `test_login_with_invalid_credentials`
  - `test_admin_can_delete_user`

### Test Organization

- One test per behavior
- Arrange-Act-Assert pattern
- Keep tests independent
- Use fixtures for setup

### Assertions

```python
# Good: Specific assertions
assert user.email == "test@example.com"
assert response.status_code == 200

# Bad: Generic assertions
assert user
assert response
```

### Test Data

- Use realistic but minimal data
- Don't hardcode IDs
- Create via fixtures
- Clean up after tests

## Continuous Integration

Tests run automatically on:

- Every commit (if CI configured)
- Pull requests
- Before deployment

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v2
    - uses: actions/setup-python@v2
      with:
        python-version: '3.10'

    - name: Install dependencies
      run: |
        pip install -r requirements.txt

    - name: Run tests
      run: pytest --cov=app
```

## Debugging Tests

### Print Debug Info

```python
def test_example(capsys):
    """Test with debug output."""
    print("Debug info")
    result = function()

    captured = capsys.readouterr()
    assert "Debug" in captured.out
```

### Interactive Debugging

```python
def test_example():
    """Test with breakpoint."""
    result = function()

    import pdb; pdb.set_trace()  # Pause here

    assert result == expected
```

### Verbose Output

```bash
pytest -vv           # Very verbose
pytest -s            # Show print statements
pytest --tb=long     # Long tracebacks
```

## Performance Testing

```python
import time

def test_performance():
    """Test that operation completes quickly."""
    start = time.time()

    # Operation to test
    result = expensive_operation()

    duration = time.time() - start
    assert duration < 1.0  # Should take less than 1 second
```

## Code Coverage

Aim for high coverage but focus on critical paths:

- Authentication flows
- Data integrity
- Security features
- Core business logic

Don't obsess over 100% coverage:

- Some code is hard to test (external APIs)
- Tests should be valuable, not just for coverage
- Focus on important functionality
