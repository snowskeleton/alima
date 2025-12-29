# Contributing

Guidelines for contributing to Alima.

## Getting Started

1. Fork the repository
2. Clone your fork
3. Create a virtual environment
4. Install dependencies
5. Create a feature branch

```bash
git clone https://github.com/yourusername/alima2.0.git
cd alima2.0
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
git checkout -b feature/my-feature
```

## Development Workflow

### 1. Make Changes

- Write code following the project style
- Add tests for new functionality
- Update documentation

### 2. Run Tests

```bash
pytest
```

All tests must pass before submitting.

### 3. Check Code Style

```bash
# Format with black (if configured)
black app/

# Type check with mypy (if configured)
mypy app/
```

### 4. Commit Changes

Use clear, descriptive commit messages:

```bash
git add .
git commit -m "Add feature: user profile settings"
```

Commit message format:

- Start with a verb (Add, Fix, Update, Remove)
- Be specific about what changed
- Reference issues: "Fix #123: ..."

### 5. Push and Create PR

```bash
git push origin feature/my-feature
```

Then create a Pull Request on GitHub.

## Code Style

### Python Style

- Follow PEP 8
- Use type hints
- Write docstrings (Google style)
- Keep functions focused and small

Example:

```python
def create_user(
    email: str,
    password: str,
    role: UserRole = UserRole.USER,
) -> User:
    """
    Create a new user account.

    Args:
        email: User's email address
        password: Plain text password (will be hashed)
        role: User role (default: USER)

    Returns:
        Created user instance

    Raises:
        ValueError: If email is invalid or already exists
    """
    # Implementation
```

### Async/Await

Use async for I/O operations:

```python
# Good
async def send_email(recipient: str) -> bool:
    await aiosmtplib.send(...)

# Bad
def send_email(recipient: str) -> bool:
    # Blocking operation
    smtplib.send(...)
```

### Database Queries

Use SQLAlchemy 2.0 style:

```python
# Good
user = db.query(User).filter(User.email == email).first()

# Also good (select API)
from sqlalchemy import select
stmt = select(User).where(User.email == email)
user = db.execute(stmt).scalar_one_or_none()
```

### Type Hints

Always use type hints:

```python
# Good
def process_book(book_id: int, db: Session) -> Audiobook | None:
    ...

# Bad
def process_book(book_id, db):
    ...
```

## Testing Requirements

### Coverage

- Add tests for all new features
- Maintain existing test coverage
- Aim for >80% coverage on new code

### Test Types

- Unit tests for services
- Integration tests for routers
- End-to-end tests for workflows

### Example Test

```python
def test_create_user(db):
    """Test user creation."""
    user = create_user(
        email="test@example.com",
        password="password123",
        role=UserRole.USER,
    )

    assert user.id is not None
    assert user.email == "test@example.com"
    assert user.role == UserRole.USER
```

## Documentation

Update documentation for:

- New features
- API changes
- Configuration options
- User-facing changes

Documentation lives in `docs/`:

- User guides in `docs/user-guide/`
- API docs in `docs/api/`
- Development docs in `docs/development/`

## Pull Request Guidelines

### Before Submitting

- [ ] All tests pass
- [ ] New tests added for new features
- [ ] Documentation updated
- [ ] Code follows style guidelines
- [ ] Commit messages are clear

### PR Description

Include:

- What the PR does
- Why the change is needed
- How to test the changes
- Screenshots (for UI changes)
- Related issues

Example:

```markdown
## Description
Add user profile settings page where users can update their email and password.

## Motivation
Users currently cannot change their password without admin intervention.

## Changes
- Added `/profile` route
- Added profile settings template
- Added password change functionality
- Updated navigation to include profile link

## Testing
1. Log in as a user
2. Navigate to Profile
3. Change password
4. Log out and log back in with new password

## Screenshots
[Screenshot of profile page]

Fixes #42
```

### Review Process

1. Submit PR
2. Automated tests run
3. Code review by maintainers
4. Address feedback
5. Approval and merge

## Feature Requests

To propose a new feature:

1. Open a GitHub issue
2. Describe the feature
3. Explain the use case
4. Discuss implementation approaches

Wait for feedback before implementing.

## Bug Reports

To report a bug:

1. Search existing issues first
2. Open a new issue with:
   - Description of the bug
   - Steps to reproduce
   - Expected behavior
   - Actual behavior
   - Environment (OS, Python version)
   - Logs (if applicable)

## Code of Conduct

- Be respectful and inclusive
- Welcome newcomers
- Focus on constructive feedback
- Assume good intentions

## Questions?

- Open a GitHub issue for questions
- Use Discussions for general topics
- Check existing documentation first

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
