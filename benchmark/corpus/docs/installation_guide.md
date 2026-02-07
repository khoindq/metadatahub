# Installation Guide

This guide covers the complete installation process for TechCorp Platform across different environments.

## Table of Contents

1. [System Requirements](#system-requirements)
2. [Quick Install](#quick-install)
3. [Detailed Installation](#detailed-installation)
4. [Configuration](#configuration)
5. [Verification](#verification)
6. [Troubleshooting](#troubleshooting)

## System Requirements

### Minimum Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | 2 cores | 4+ cores |
| RAM | 4 GB | 8+ GB |
| Disk | 20 GB | 50+ GB SSD |
| Python | 3.10 | 3.11+ |

### Supported Operating Systems

- **Linux**: Ubuntu 20.04+, Debian 11+, CentOS 8+, RHEL 8+
- **macOS**: 12.0 (Monterey) or later
- **Windows**: Windows 10/11 with WSL2

### Required Dependencies

- Python 3.10 or higher
- pip 21.0 or higher
- Git 2.30 or higher
- (Optional) Docker 20.10+ for containerized deployment

## Quick Install

### One-Line Install (Linux/macOS)

```bash
curl -sSL https://install.techcorp.example.com | bash
```

### Using pip

```bash
pip install techcorp-platform
```

### Using Docker

```bash
docker run -d -p 8080:8080 techcorp/platform:latest
```

## Detailed Installation

### Step 1: Clone the Repository

```bash
git clone https://github.com/techcorp/platform.git
cd platform
```

### Step 2: Create Virtual Environment

```bash
# Create virtual environment
python -m venv venv

# Activate on Linux/macOS
source venv/bin/activate

# Activate on Windows
.\venv\Scripts\activate
```

### Step 3: Install Dependencies

```bash
# Install core dependencies
pip install -r requirements.txt

# Install development dependencies (optional)
pip install -r requirements-dev.txt
```

### Step 4: Install the Package

```bash
# Install in development mode
pip install -e .

# Or install normally
pip install .
```

### Step 5: Initialize Configuration

```bash
# Generate default config file
techcorp init

# Or specify custom location
techcorp init --config ~/.techcorp/config.yaml
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `TECHCORP_HOME` | Base directory | `~/.techcorp` |
| `TECHCORP_ENV` | Environment (dev/staging/prod) | `dev` |
| `TECHCORP_LOG_LEVEL` | Logging level | `INFO` |
| `TECHCORP_API_KEY` | API key for cloud features | (none) |
| `TECHCORP_DB_URL` | Database connection string | `sqlite:///data.db` |

### Configuration File

Create `~/.techcorp/config.yaml`:

```yaml
# TechCorp Platform Configuration

server:
  host: 0.0.0.0
  port: 8080
  workers: 4
  timeout: 30

database:
  url: postgresql://user:pass@localhost/techcorp
  pool_size: 10
  max_overflow: 20

logging:
  level: INFO
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  file: ~/.techcorp/logs/app.log

features:
  enable_telemetry: true
  enable_cache: true
  cache_ttl: 3600

security:
  secret_key: ${TECHCORP_SECRET_KEY}  # Use environment variable
  session_timeout: 86400
  rate_limit: 1000  # requests per minute
```

### Database Setup

#### SQLite (Default)

No additional setup required. Database file created automatically.

#### PostgreSQL

```bash
# Install PostgreSQL
sudo apt install postgresql postgresql-contrib

# Create database
sudo -u postgres createdb techcorp

# Create user
sudo -u postgres createuser --pwprompt techcorp_user

# Grant permissions
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE techcorp TO techcorp_user;"
```

#### MySQL

```bash
# Install MySQL
sudo apt install mysql-server

# Create database and user
mysql -u root -p << EOF
CREATE DATABASE techcorp CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'techcorp_user'@'localhost' IDENTIFIED BY 'your_password';
GRANT ALL PRIVILEGES ON techcorp.* TO 'techcorp_user'@'localhost';
FLUSH PRIVILEGES;
EOF
```

### Running Migrations

```bash
# Run all pending migrations
techcorp db migrate

# Check migration status
techcorp db status

# Rollback last migration
techcorp db rollback
```

## Verification

### Check Installation

```bash
# Verify installation
techcorp --version
# Output: TechCorp Platform v2.1.0

# Run health check
techcorp health
# Output: All systems operational

# Check configuration
techcorp config show
```

### Run Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=techcorp --cov-report=html

# Run specific test file
pytest tests/test_auth.py -v
```

### Start Development Server

```bash
# Start in development mode
techcorp serve --dev

# Start with auto-reload
techcorp serve --dev --reload

# Start with specific port
techcorp serve --port 3000
```

## Troubleshooting

### Common Issues

#### Issue: `ModuleNotFoundError: No module named 'techcorp'`

**Solution**: Ensure virtual environment is activated and package is installed:

```bash
source venv/bin/activate
pip install -e .
```

#### Issue: `Permission denied` when writing to config directory

**Solution**: Fix permissions or use a different directory:

```bash
mkdir -p ~/.techcorp
chmod 755 ~/.techcorp
```

#### Issue: Database connection failed

**Solution**: Verify database is running and credentials are correct:

```bash
# Test PostgreSQL connection
psql -h localhost -U techcorp_user -d techcorp

# Test MySQL connection
mysql -h localhost -u techcorp_user -p techcorp
```

#### Issue: Port already in use

**Solution**: Use a different port or kill existing process:

```bash
# Find process using port
lsof -i :8080

# Kill process
kill -9 <PID>

# Or use different port
techcorp serve --port 8081
```

### Getting Help

- **Documentation**: https://docs.techcorp.example.com
- **GitHub Issues**: https://github.com/techcorp/platform/issues
- **Discord**: https://discord.gg/techcorp
- **Email**: support@techcorp.example.com

### Log Files

Logs are stored in `~/.techcorp/logs/`:

- `app.log` - Application logs
- `error.log` - Error logs only
- `access.log` - HTTP access logs

View recent logs:

```bash
tail -f ~/.techcorp/logs/app.log
```

---

*Last Updated: October 2024*
*Version: 2.1.0*
