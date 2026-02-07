# API Reference

Complete API documentation for TechCorp Platform REST API.

## Base URL

```
Production: https://api.techcorp.example.com/v1
Staging:    https://api-staging.techcorp.example.com/v1
```

## Authentication

All API requests require authentication using Bearer tokens.

### Get Access Token

```http
POST /auth/token
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "your_password"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "Bearer",
  "expires_in": 86400,
  "refresh_token": "dGhpcyBpcyBhIHJlZnJlc2g..."
}
```

### Using the Token

Include in all requests:

```http
Authorization: Bearer <access_token>
```

### Refresh Token

```http
POST /auth/refresh
Content-Type: application/json

{
  "refresh_token": "dGhpcyBpcyBhIHJlZnJlc2g..."
}
```

## Rate Limiting

| Plan | Requests/minute | Requests/day |
|------|-----------------|--------------|
| Free | 60 | 1,000 |
| Pro | 300 | 50,000 |
| Enterprise | 1,000 | Unlimited |

Rate limit headers:
- `X-RateLimit-Limit`: Max requests per window
- `X-RateLimit-Remaining`: Remaining requests
- `X-RateLimit-Reset`: Unix timestamp when limit resets

## Endpoints

### Users

#### List Users

```http
GET /users
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `page` | integer | Page number (default: 1) |
| `per_page` | integer | Items per page (default: 20, max: 100) |
| `role` | string | Filter by role (admin, user, guest) |
| `status` | string | Filter by status (active, inactive) |
| `search` | string | Search by name or email |

**Response:**
```json
{
  "data": [
    {
      "id": "usr_abc123",
      "email": "alice@example.com",
      "name": "Alice Johnson",
      "role": "admin",
      "status": "active",
      "created_at": "2024-01-15T10:30:00Z",
      "last_login": "2024-10-20T14:22:00Z"
    }
  ],
  "pagination": {
    "page": 1,
    "per_page": 20,
    "total": 150,
    "total_pages": 8
  }
}
```

#### Get User

```http
GET /users/{user_id}
```

**Response:**
```json
{
  "id": "usr_abc123",
  "email": "alice@example.com",
  "name": "Alice Johnson",
  "role": "admin",
  "status": "active",
  "created_at": "2024-01-15T10:30:00Z",
  "last_login": "2024-10-20T14:22:00Z",
  "metadata": {
    "department": "Engineering",
    "location": "San Francisco"
  },
  "permissions": ["read:all", "write:all", "admin:users"]
}
```

#### Create User

```http
POST /users
Content-Type: application/json

{
  "email": "newuser@example.com",
  "name": "New User",
  "password": "securepassword123",
  "role": "user"
}
```

**Response:** `201 Created`
```json
{
  "id": "usr_xyz789",
  "email": "newuser@example.com",
  "name": "New User",
  "role": "user",
  "status": "active",
  "created_at": "2024-10-25T09:15:00Z"
}
```

#### Update User

```http
PATCH /users/{user_id}
Content-Type: application/json

{
  "name": "Updated Name",
  "role": "admin"
}
```

**Response:** `200 OK`

#### Delete User

```http
DELETE /users/{user_id}
```

**Response:** `204 No Content`

### Projects

#### List Projects

```http
GET /projects
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `page` | integer | Page number |
| `per_page` | integer | Items per page |
| `owner_id` | string | Filter by owner |
| `status` | string | active, archived, deleted |
| `sort` | string | created_at, updated_at, name |
| `order` | string | asc, desc |

**Response:**
```json
{
  "data": [
    {
      "id": "prj_abc123",
      "name": "Project Alpha",
      "description": "Main product development",
      "owner_id": "usr_xyz789",
      "status": "active",
      "created_at": "2024-03-01T00:00:00Z",
      "updated_at": "2024-10-20T15:30:00Z",
      "stats": {
        "members": 12,
        "tasks": 156,
        "completed_tasks": 89
      }
    }
  ],
  "pagination": { ... }
}
```

#### Create Project

```http
POST /projects
Content-Type: application/json

{
  "name": "New Project",
  "description": "Project description",
  "settings": {
    "visibility": "private",
    "enable_notifications": true
  }
}
```

#### Get Project

```http
GET /projects/{project_id}
```

#### Update Project

```http
PATCH /projects/{project_id}
Content-Type: application/json

{
  "name": "Updated Project Name",
  "description": "New description"
}
```

#### Delete Project

```http
DELETE /projects/{project_id}
```

#### Add Project Member

```http
POST /projects/{project_id}/members
Content-Type: application/json

{
  "user_id": "usr_abc123",
  "role": "editor"
}
```

### Documents

#### Upload Document

```http
POST /documents
Content-Type: multipart/form-data

file: (binary)
project_id: prj_abc123
folder: /reports/q3
```

**Response:**
```json
{
  "id": "doc_xyz789",
  "name": "report.pdf",
  "size": 1048576,
  "mime_type": "application/pdf",
  "project_id": "prj_abc123",
  "path": "/reports/q3/report.pdf",
  "created_at": "2024-10-25T10:00:00Z",
  "url": "https://cdn.techcorp.example.com/docs/doc_xyz789"
}
```

#### List Documents

```http
GET /projects/{project_id}/documents
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `folder` | string | Filter by folder path |
| `mime_type` | string | Filter by MIME type |
| `search` | string | Search in filename |

#### Get Document

```http
GET /documents/{document_id}
```

#### Download Document

```http
GET /documents/{document_id}/download
```

**Response:** Binary file with appropriate Content-Type

#### Delete Document

```http
DELETE /documents/{document_id}
```

### Search

#### Full-Text Search

```http
POST /search
Content-Type: application/json

{
  "query": "quarterly revenue report",
  "filters": {
    "project_id": "prj_abc123",
    "type": ["document", "task"],
    "date_range": {
      "start": "2024-01-01",
      "end": "2024-12-31"
    }
  },
  "page": 1,
  "per_page": 20
}
```

**Response:**
```json
{
  "results": [
    {
      "type": "document",
      "id": "doc_abc123",
      "title": "Q3 Revenue Report",
      "snippet": "...quarterly revenue increased by 23%...",
      "score": 0.95,
      "url": "/documents/doc_abc123"
    }
  ],
  "total": 42,
  "took_ms": 45
}
```

### Analytics

#### Get Dashboard Stats

```http
GET /analytics/dashboard
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `period` | string | day, week, month, year |
| `project_id` | string | Filter by project |

**Response:**
```json
{
  "period": "month",
  "metrics": {
    "active_users": 1250,
    "documents_created": 3420,
    "api_calls": 1250000,
    "storage_used_gb": 245.6
  },
  "trends": {
    "users": "+12%",
    "documents": "+8%",
    "api_calls": "+25%"
  }
}
```

#### Get Usage Report

```http
GET /analytics/usage
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `start_date` | string | ISO date |
| `end_date` | string | ISO date |
| `granularity` | string | hour, day, week |

## Webhooks

### Register Webhook

```http
POST /webhooks
Content-Type: application/json

{
  "url": "https://your-server.com/webhook",
  "events": ["user.created", "document.uploaded", "project.updated"],
  "secret": "your_webhook_secret"
}
```

### Webhook Events

| Event | Description |
|-------|-------------|
| `user.created` | New user registered |
| `user.updated` | User profile updated |
| `user.deleted` | User account deleted |
| `project.created` | New project created |
| `project.updated` | Project settings changed |
| `project.deleted` | Project deleted |
| `document.uploaded` | New document uploaded |
| `document.deleted` | Document removed |

### Webhook Payload

```json
{
  "event": "document.uploaded",
  "timestamp": "2024-10-25T10:30:00Z",
  "data": {
    "id": "doc_abc123",
    "name": "report.pdf",
    "project_id": "prj_xyz789"
  }
}
```

### Verify Webhook Signature

```python
import hmac
import hashlib

def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)
```

## Error Handling

### Error Response Format

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed",
    "details": [
      {
        "field": "email",
        "message": "Invalid email format"
      }
    ]
  },
  "request_id": "req_abc123xyz"
}
```

### Error Codes

| HTTP Status | Code | Description |
|-------------|------|-------------|
| 400 | `BAD_REQUEST` | Invalid request format |
| 400 | `VALIDATION_ERROR` | Request validation failed |
| 401 | `UNAUTHORIZED` | Missing or invalid token |
| 403 | `FORBIDDEN` | Insufficient permissions |
| 404 | `NOT_FOUND` | Resource not found |
| 409 | `CONFLICT` | Resource already exists |
| 429 | `RATE_LIMITED` | Too many requests |
| 500 | `INTERNAL_ERROR` | Server error |

## SDKs

Official SDKs available:

- **Python**: `pip install techcorp-sdk`
- **JavaScript**: `npm install @techcorp/sdk`
- **Go**: `go get github.com/techcorp/sdk-go`
- **Ruby**: `gem install techcorp-sdk`

### Python Example

```python
from techcorp import Client

client = Client(api_key="your_api_key")

# List users
users = client.users.list(page=1, per_page=20)

# Create project
project = client.projects.create(
    name="My Project",
    description="Project description"
)

# Upload document
doc = client.documents.upload(
    file_path="./report.pdf",
    project_id=project.id
)
```

---

*API Version: v1*
*Last Updated: October 2024*
