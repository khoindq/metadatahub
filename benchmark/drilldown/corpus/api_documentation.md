# API Reference

Welcome to the Enterprise API Documentation. This reference covers all available endpoints, authentication methods, and data operations for version 2.3 of our REST API.

**Base URL:** `https://api.example.com/v2`

**API Version:** 2.3.0

---

## Authentication

All API requests require authentication. We support multiple authentication methods depending on your use case.

### Login Endpoint

The login endpoint authenticates a user and returns access tokens for subsequent API calls.

**Endpoint:** `POST /auth/login`

#### Request Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| username | string | Yes | User's login username (3-50 characters) |
| password | string | Yes | User's password (min 12 characters) |
| remember_me | boolean | No | If true, refresh token TTL is extended to 30 days |
| device_id | string | No | Unique device identifier for session tracking |
| mfa_code | string | Conditional | Required if user has MFA enabled |

**Content-Type:** `application/json`

**Example Request:**
```json
{
  "username": "john.doe",
  "password": "SecurePassword123!",
  "remember_me": true,
  "device_id": "mobile-ios-abc123"
}
```

#### Response Format

**Success Response (200 OK):**

| Field | Type | Description |
|-------|------|-------------|
| access_token | string | JWT token for API access (expires in 15 minutes) |
| refresh_token | string | Token for refreshing access (expires in 7 days) |
| token_type | string | Always "Bearer" |
| expires_in | integer | Access token TTL in seconds |
| user | object | User profile information |

**Example Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "dGhpcyBpcyBhIHJlZnJl...",
  "token_type": "Bearer",
  "expires_in": 900,
  "user": {
    "id": "usr_abc123",
    "username": "john.doe",
    "email": "john@example.com",
    "roles": ["user", "editor"]
  }
}
```

**Error Responses:**

| Status | Error Code | Description |
|--------|------------|-------------|
| 400 | INVALID_REQUEST | Missing or malformed parameters |
| 401 | INVALID_CREDENTIALS | Wrong username or password |
| 403 | ACCOUNT_LOCKED | Too many failed attempts |
| 403 | MFA_REQUIRED | MFA code is required but not provided |

### Token Refresh

Refresh your access token using a valid refresh token.

**Endpoint:** `POST /auth/refresh`

#### Request Body

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| refresh_token | string | Yes | Valid refresh token from login |

#### Response

Returns the same format as the login endpoint with new access and refresh tokens.

**Note:** The old refresh token is invalidated after use.

### Logout

Invalidate the current access token.

**Endpoint:** `POST /auth/logout`

#### Headers

| Header | Value | Description |
|--------|-------|-------------|
| Authorization | Bearer {token} | Access token to invalidate |

#### Response

**Success (204 No Content):** Token successfully invalidated.

### API Keys

For server-to-server authentication, use API keys instead of user tokens.

**Endpoint:** `POST /auth/api-keys`

#### Create API Key

**Request:**
```json
{
  "name": "Production Server",
  "permissions": ["read:data", "write:data"],
  "expires_in_days": 365
}
```

**Response:**
```json
{
  "key_id": "key_xyz789",
  "api_key": "sk_live_abc123...",
  "name": "Production Server",
  "permissions": ["read:data", "write:data"],
  "expires_at": "2025-02-07T00:00:00Z"
}
```

**Important:** The `api_key` is only shown once. Store it securely.

---

## Data Operations

The Data Operations API allows you to create, read, update, and delete records in your data store.

### Create Record

Create a new record in a specified collection.

**Endpoint:** `POST /data/{collection}`

#### Path Parameters

| Parameter | Description |
|-----------|-------------|
| collection | Name of the collection (e.g., "users", "products") |

#### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| data | object | Yes | Record data (schema depends on collection) |
| metadata | object | No | Additional metadata (tags, labels) |
| ttl | integer | No | Time-to-live in seconds (auto-delete) |

**Example Request:**
```json
{
  "data": {
    "name": "Widget Pro",
    "price": 29.99,
    "category": "electronics",
    "in_stock": true
  },
  "metadata": {
    "tags": ["featured", "new"],
    "source": "import_batch_001"
  }
}
```

#### Response

**Success (201 Created):**
```json
{
  "id": "rec_abc123",
  "collection": "products",
  "data": {
    "name": "Widget Pro",
    "price": 29.99,
    "category": "electronics",
    "in_stock": true
  },
  "metadata": {
    "tags": ["featured", "new"],
    "source": "import_batch_001"
  },
  "created_at": "2024-02-07T10:30:00Z",
  "updated_at": "2024-02-07T10:30:00Z"
}
```

### Query Records

Retrieve records from a collection with filtering, sorting, and pagination.

**Endpoint:** `GET /data/{collection}`

#### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| filter | string | - | Filter expression (see Filter Syntax below) |
| sort | string | created_at | Field to sort by |
| order | string | desc | Sort order: "asc" or "desc" |
| limit | integer | 20 | Records per page (max 100) |
| offset | integer | 0 | Number of records to skip |
| fields | string | - | Comma-separated list of fields to return |

#### Filter Syntax

Filters use a simple query language:

| Operator | Example | Description |
|----------|---------|-------------|
| eq | `status:eq:active` | Equals |
| ne | `type:ne:draft` | Not equals |
| gt | `price:gt:100` | Greater than |
| gte | `count:gte:5` | Greater than or equal |
| lt | `age:lt:30` | Less than |
| lte | `score:lte:50` | Less than or equal |
| in | `status:in:active,pending` | In list |
| contains | `name:contains:widget` | Contains substring |

Multiple filters are combined with `AND`. Separate filters with `;`.

**Example:** `status:eq:active;price:gt:10;category:in:electronics,gadgets`

#### Response

```json
{
  "data": [
    {
      "id": "rec_abc123",
      "data": { ... },
      "created_at": "2024-02-07T10:30:00Z"
    }
  ],
  "pagination": {
    "total": 150,
    "limit": 20,
    "offset": 0,
    "has_more": true
  }
}
```

### Update Record

Update an existing record by ID.

**Endpoint:** `PUT /data/{collection}/{id}`

#### Request Body

Same format as Create Record. All provided fields will be updated.

**Partial Update:** Use `PATCH` instead of `PUT` to update only specific fields.

### Delete Record

Delete a record by ID.

**Endpoint:** `DELETE /data/{collection}/{id}`

#### Response

**Success (204 No Content):** Record deleted.

**Error (404 Not Found):** Record not found.

---

## Batch Operations

For high-volume operations, use batch endpoints.

### Batch Create

Create multiple records in a single request.

**Endpoint:** `POST /data/{collection}/batch`

**Request:**
```json
{
  "records": [
    { "data": { "name": "Item 1" } },
    { "data": { "name": "Item 2" } },
    { "data": { "name": "Item 3" } }
  ]
}
```

**Response:**
```json
{
  "created": 3,
  "failed": 0,
  "records": [ ... ]
}
```

**Limits:** Maximum 1000 records per batch request.

### Batch Delete

Delete multiple records by IDs.

**Endpoint:** `POST /data/{collection}/batch-delete`

**Request:**
```json
{
  "ids": ["rec_abc123", "rec_def456", "rec_ghi789"]
}
```

---

## Webhooks

Configure webhooks to receive real-time notifications when data changes.

### Register Webhook

**Endpoint:** `POST /webhooks`

**Request:**
```json
{
  "url": "https://your-server.com/webhook",
  "events": ["record.created", "record.updated", "record.deleted"],
  "collections": ["products", "orders"],
  "secret": "your_webhook_secret"
}
```

### Webhook Payload

```json
{
  "event": "record.created",
  "timestamp": "2024-02-07T10:30:00Z",
  "data": {
    "collection": "products",
    "record_id": "rec_abc123",
    "changes": { ... }
  },
  "signature": "sha256=abc123..."
}
```

---

## Rate Limits

API requests are rate-limited based on your plan:

| Plan | Requests/minute | Requests/day |
|------|-----------------|--------------|
| Free | 60 | 10,000 |
| Pro | 300 | 100,000 |
| Enterprise | 1000 | Unlimited |

**Rate Limit Headers:**
- `X-RateLimit-Limit`: Maximum requests allowed
- `X-RateLimit-Remaining`: Requests remaining in window
- `X-RateLimit-Reset`: Unix timestamp when limit resets

---

## Error Handling

All errors follow a consistent format:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable error message",
    "details": { ... }
  }
}
```

### Common Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| INVALID_REQUEST | 400 | Malformed request body or parameters |
| UNAUTHORIZED | 401 | Missing or invalid authentication |
| FORBIDDEN | 403 | Authenticated but lacking permission |
| NOT_FOUND | 404 | Resource not found |
| RATE_LIMITED | 429 | Too many requests |
| INTERNAL_ERROR | 500 | Server error (retry later) |

---

## SDK Support

Official SDKs are available for:

- **Python:** `pip install example-api`
- **JavaScript/Node.js:** `npm install @example/api-client`
- **Go:** `go get github.com/example/api-go`
- **Ruby:** `gem install example-api`

See the [SDK documentation](https://docs.example.com/sdks) for language-specific guides.
