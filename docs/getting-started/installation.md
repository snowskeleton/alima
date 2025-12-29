# Installation

This guide will help you install and run Alima 2.0 on your system.

## Prerequisites

- Python 3.10 or higher
- pip (Python package manager)
- 2GB+ free disk space (for audiobooks)

## Installation Steps

### 1. Clone or Download

If you have the source code, navigate to the project directory:

```bash
cd /path/to/alima2.0
```

### 2. Create Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

!!! tip "Windows Users"
    On Windows, use `.venv\Scripts\activate` instead of `source .venv/bin/activate`

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env` and set the required variables:

```bash
nano .env  # or use your preferred editor
```

**Required settings:**

- `SECRET_KEY` - Generate a random secret key:
  ```bash
  openssl rand -hex 32
  ```

- `DOMAIN` - The URL where Alima will be accessible:
  ```
  DOMAIN=http://localhost:8000
  ```

See [Configuration Guide](configuration.md) for all available options.

### 5. Run the Application

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The application will be available at: **http://localhost:8000**

!!! success "First Run"
    On first run, Alima will automatically:

    - Create the SQLite database
    - Set up data directories
    - Start the background sync scheduler

## Verify Installation

1. Open http://localhost:8000/health in your browser
2. You should see a JSON response with `"status": "healthy"`
3. Visit http://localhost:8000 to access the login page

## Next Steps

- [Create your first user account](first-run.md)
- [Configure server settings](../user-guide/server-settings.md)
- [Add an Audible account](../user-guide/audible-accounts.md)

## Troubleshooting

### "Module not found" errors

Make sure your virtual environment is activated:

```bash
source .venv/bin/activate
```

### Port already in use

Use a different port:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

### Permission errors

Make sure the data directory is writable:

```bash
mkdir -p data/{db,audiobooks,covers,audible_auth,temp}
chmod -R 755 data
```
