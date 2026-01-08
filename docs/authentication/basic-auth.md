# Basic Authentication

Basic Authentication (Basic Auth) is a simple authentication method that uses username and password credentials sent with HTTP requests. It's supported by many web services and databases.

## Overview

Basic Authentication:
- Uses username and password
- Sent as Base64-encoded header
- Supported by HTTP/HTTPS
- Simple to implement
- Widely compatible

## Crawlers Using Basic Auth

| Crawler | Use Case | Documentation |
|---------|----------|---------------|
| **Website** | HTTP Basic Auth sites | [Guide](../crawlers/website.md) |
| **Database** | Database connections | [Guide](../crawlers/database.md) |

---

## Website Basic Authentication

### Step 1: Add Credentials to secrets.toml

```toml
[default]
HTTP_USERNAME = "your-username"
HTTP_PASSWORD = "your-password"
```

### Step 2: Configure Website Crawler

```yaml
website_crawler:
  urls:
    - "https://docs.example.com"

  # Enable basic auth
  auth_type: "basic"

  # Credential variable names
  username_var: "HTTP_USERNAME"
  password_var: "HTTP_PASSWORD"
```

### Step 3: Run Crawler

```bash
python3 -m vectara_ingest --config config/website.yaml
```

The crawler will:
1. Load credentials from secrets.toml
2. Add Authorization header to requests
3. Access protected content
4. Start indexing

---

## Database Authentication

Databases typically use username/password authentication similar to Basic Auth.

### PostgreSQL

```toml
[default]
DB_USERNAME = "postgres_user"
DB_PASSWORD = "postgres_password"
```

```yaml
database_crawler:
  db_type: "postgresql"
  host: "localhost"
  port: 5432
  database: "mydb"
  username_var: "DB_USERNAME"
  password_var: "DB_PASSWORD"

  query: "SELECT * FROM documents"
```

### MySQL

```toml
[default]
MYSQL_USERNAME = "root"
MYSQL_PASSWORD = "mysql_password"
```

```yaml
database_crawler:
  db_type: "mysql"
  host: "localhost"
  port: 3306
  database: "mydb"
  username_var: "MYSQL_USERNAME"
  password_var: "MYSQL_PASSWORD"

  query: "SELECT * FROM articles"
```

### SQL Server

```toml
[default]
MSSQL_USERNAME = "sa"
MSSQL_PASSWORD = "sqlserver_password"
```

```yaml
database_crawler:
  db_type: "mssql"
  host: "localhost"
  port: 1433
  database: "mydb"
  username_var: "MSSQL_USERNAME"
  password_var: "MSSQL_PASSWORD"

  query: "SELECT * FROM content"
```

---

## Configuration Examples

### Simple Website with Basic Auth

```yaml
website_crawler:
  urls:
    - "https://internal.company.com/docs"

  auth_type: "basic"
  username_var: "HTTP_USERNAME"
  password_var: "HTTP_PASSWORD"

  # Standard crawling options
  max_depth: 3
  scrape_method: "scrapy"
```

### Multiple Sites with Different Credentials

```toml
# secrets.toml
[default]
SITE1_USERNAME = "user1"
SITE1_PASSWORD = "pass1"
SITE2_USERNAME = "user2"
SITE2_PASSWORD = "pass2"
```

**Site 1 Config:**
```yaml
website_crawler:
  urls:
    - "https://site1.com"
  auth_type: "basic"
  username_var: "SITE1_USERNAME"
  password_var: "SITE1_PASSWORD"
```

**Site 2 Config:**
```yaml
website_crawler:
  urls:
    - "https://site2.com"
  auth_type: "basic"
  username_var: "SITE2_USERNAME"
  password_var: "SITE2_PASSWORD"
```

### Database with SSL

```yaml
database_crawler:
  db_type: "postgresql"
  host: "db.company.com"
  port: 5432
  database: "production"
  username_var: "DB_USERNAME"
  password_var: "DB_PASSWORD"

  # SSL configuration
  ssl_mode: "require"
  ssl_cert: "/path/to/client-cert.pem"
  ssl_key: "/path/to/client-key.pem"
  ssl_ca: "/path/to/ca-cert.pem"
```

---

## Security Best Practices

### Credential Storage

**Store in secrets.toml:**
```toml
[default]
username = "your-username"
password = "your-password"
```

**File Permissions:**
```bash
chmod 600 secrets.toml
```

**Git Ignore:**
```gitignore
secrets.toml
*.password
*.credentials
```

### HTTPS/SSL

**Always use HTTPS for Basic Auth:**
```yaml
website_crawler:
  urls:
    - "https://secure-site.com"  # ✅ HTTPS
    # NOT http://  # ❌ Insecure

  auth_type: "basic"
```

Basic Auth over HTTP sends credentials in cleartext!

### Password Rotation

**Rotate credentials regularly:**
1. Generate new password
2. Update secrets.toml
3. Test crawler
4. Update old systems

**For databases:**
```sql
-- PostgreSQL
ALTER USER myuser WITH PASSWORD 'new-password';

-- MySQL
ALTER USER 'myuser'@'localhost' IDENTIFIED BY 'new-password';
```

---

## Troubleshooting

### "401 Unauthorized"

**Causes:**
- Wrong username or password
- Credentials not in secrets.toml
- Wrong variable names in config

**Solutions:**
1. Verify credentials work in browser
2. Check variable names match exactly
3. Ensure secrets.toml has [default] section
4. Test with curl:
   ```bash
   curl -u username:password https://site.com
   ```

### "Connection refused" (Database)

**Causes:**
- Database not running
- Wrong host/port
- Firewall blocking connection

**Solutions:**
1. Verify database is running
2. Check host and port
3. Test connection:
   ```bash
   # PostgreSQL
   psql -h localhost -p 5432 -U username -d database

   # MySQL
   mysql -h localhost -P 3306 -u username -p database
   ```

### "SSL required"

**Cause:** Database requires SSL connection

**Solution:**
```yaml
database_crawler:
  ssl_mode: "require"  # or "prefer", "verify-full"
```

### Credentials not found

**Check secrets.toml:**
```bash
cat secrets.toml
```

**Verify structure:**
```toml
[default]  # ← Section header required
USERNAME = "value"  # ← Exact variable name
PASSWORD = "value"
```

---

## Authentication Headers

### How Basic Auth Works

Basic Auth encodes credentials as:
```
Authorization: Basic base64(username:password)
```

**Example:**
```
Username: admin
Password: secret123
Encoded: YWRtaW46c2VjcmV0MTIz
Header: Authorization: Basic YWRtaW46c2VjcmV0MTIz
```

### Custom Headers

For sites requiring custom authentication headers:

```yaml
website_crawler:
  urls:
    - "https://api.example.com"

  custom_headers:
    Authorization: "Bearer ${API_TOKEN}"
    X-API-Key: "${API_KEY}"
```

```toml
[default]
API_TOKEN = "your-token"
API_KEY = "your-key"
```

---

## Comparison with Other Methods

| Feature | Basic Auth | API Keys | OAuth 2.0 | SAML |
|---------|-----------|----------|-----------|------|
| **Simplicity** | ✅ Very Simple | ✅ Simple | ⚠️ Complex | ⚠️ Complex |
| **Security** | ⚠️ HTTPS Required | ✅ Good | ✅ Excellent | ✅ Excellent |
| **Expiration** | ❌ No | ⚠️ Sometimes | ✅ Yes | ✅ Yes |
| **Revocation** | ⚠️ Change password | ✅ Easy | ✅ Easy | ✅ Easy |
| **Setup** | 1 minute | 5 minutes | 15 minutes | 30+ minutes |
| **Use Case** | Simple sites, DBs | APIs | Delegated access | Enterprise SSO |

**When to use Basic Auth:**
- ✅ Internal/dev sites
- ✅ Database connections
- ✅ Simple HTTP auth sites
- ✅ Legacy systems

**When NOT to use:**
- ❌ Production APIs (use API keys)
- ❌ User-facing auth (use OAuth)
- ❌ Enterprise sites (use SAML)

---

## Database-Specific Notes

### Connection Strings

Some databases support connection strings with embedded credentials:

**PostgreSQL:**
```yaml
connection_string: "postgresql://user:password@localhost:5432/database"
```

**MySQL:**
```yaml
connection_string: "mysql://user:password@localhost:3306/database"
```

**Prefer separate credentials:**
```yaml
username_var: "DB_USERNAME"
password_var: "DB_PASSWORD"
```
This keeps credentials in secrets.toml.

### Connection Pooling

For high-volume crawling:

```yaml
database_crawler:
  pool_size: 10
  max_overflow: 20
  pool_timeout: 30
```

---

## Related Documentation

- [Website Crawler](../crawlers/website.md)
- [Database Crawler](../crawlers/database.md)
- [API Keys Authentication](api-keys.md)
- [Secrets Management](../secrets-management.md)
- [Authentication Overview](index.md)
