# System Architecture

Technical architecture documentation for TechCorp Platform.

## Overview

TechCorp Platform is a distributed microservices architecture designed for scalability, reliability, and maintainability. This document describes the system components, data flow, and design decisions.

```
┌─────────────────────────────────────────────────────────────────┐
│                        Client Layer                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │ Web App  │  │ Mobile   │  │  CLI     │  │  SDKs    │       │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘       │
└───────┼─────────────┼─────────────┼─────────────┼──────────────┘
        │             │             │             │
        └─────────────┴──────┬──────┴─────────────┘
                             │
┌────────────────────────────┼────────────────────────────────────┐
│                    API Gateway Layer                             │
│  ┌─────────────────────────┴─────────────────────────────────┐  │
│  │                    Kong API Gateway                        │  │
│  │  • Rate Limiting  • Authentication  • Load Balancing      │  │
│  └─────────────────────────┬─────────────────────────────────┘  │
└────────────────────────────┼────────────────────────────────────┘
                             │
┌────────────────────────────┼────────────────────────────────────┐
│                    Service Layer                                 │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌──────────┐  │
│  │   Auth     │  │   User     │  │  Project   │  │ Document │  │
│  │  Service   │  │  Service   │  │  Service   │  │ Service  │  │
│  └──────┬─────┘  └──────┬─────┘  └──────┬─────┘  └────┬─────┘  │
│         │               │               │              │        │
│  ┌──────┴───────────────┴───────────────┴──────────────┴─────┐  │
│  │                    Message Bus (Kafka)                     │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌──────────┐  │
│  │  Search    │  │ Analytics  │  │ Notification│  │  Worker  │  │
│  │  Service   │  │  Service   │  │  Service   │  │ Service  │  │
│  └────────────┘  └────────────┘  └────────────┘  └──────────┘  │
└─────────────────────────────────────────────────────────────────┘
                             │
┌────────────────────────────┼────────────────────────────────────┐
│                    Data Layer                                    │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌──────────┐  │
│  │ PostgreSQL │  │   Redis    │  │Elasticsearch│  │   S3     │  │
│  │  (Primary) │  │  (Cache)   │  │  (Search)  │  │ (Storage)│  │
│  └────────────┘  └────────────┘  └────────────┘  └──────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Core Components

### API Gateway

**Technology**: Kong API Gateway

**Responsibilities**:
- Request routing to appropriate microservices
- Authentication and authorization
- Rate limiting and throttling
- Request/response transformation
- SSL termination
- Logging and metrics collection

**Configuration**:
```yaml
services:
  - name: auth-service
    url: http://auth-service:8001
    routes:
      - paths: ["/auth/*"]
  - name: user-service
    url: http://user-service:8002
    routes:
      - paths: ["/users/*"]
```

### Authentication Service

**Technology**: Python (FastAPI) + JWT

**Responsibilities**:
- User authentication (login/logout)
- Token generation and validation
- OAuth2/OIDC integration
- Session management
- Multi-factor authentication

**Key Classes**:
- `AuthService`: Main authentication logic
- `TokenManager`: JWT token handling
- `PasswordHasher`: Secure password hashing (PBKDF2)
- `OAuthProvider`: Third-party authentication

**API Endpoints**:
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/auth/token` | POST | Get access token |
| `/auth/refresh` | POST | Refresh token |
| `/auth/logout` | POST | Invalidate token |
| `/auth/mfa/setup` | POST | Setup MFA |

### User Service

**Technology**: Python (FastAPI) + PostgreSQL

**Responsibilities**:
- User CRUD operations
- Profile management
- Role and permission management
- User preferences

**Database Schema**:
```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    username VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) DEFAULT 'user',
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE user_permissions (
    user_id UUID REFERENCES users(id),
    permission VARCHAR(100) NOT NULL,
    granted_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (user_id, permission)
);
```

### Document Service

**Technology**: Python (FastAPI) + S3 + PostgreSQL

**Responsibilities**:
- File upload and download
- Metadata management
- Version control
- Access control
- Format conversion

**Storage Strategy**:
- Metadata → PostgreSQL
- File content → S3 (with CDN)
- Thumbnails → S3 (separate bucket)

**Processing Pipeline**:
```
Upload → Validation → Virus Scan → Store → Index → Thumbnail → Notify
```

### Search Service

**Technology**: Python + Elasticsearch

**Responsibilities**:
- Full-text search
- Faceted search
- Auto-complete
- Search analytics

**Index Configuration**:
```json
{
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "analyzer": "standard",
        "fields": {
          "keyword": { "type": "keyword" }
        }
      },
      "content": {
        "type": "text",
        "analyzer": "english"
      },
      "tags": { "type": "keyword" },
      "created_at": { "type": "date" }
    }
  }
}
```

## Data Flow

### User Authentication Flow

```
1. Client sends credentials to /auth/token
2. API Gateway routes to Auth Service
3. Auth Service validates credentials against User Service
4. On success, JWT token generated and returned
5. Client includes token in subsequent requests
6. API Gateway validates token before routing
```

### Document Upload Flow

```
1. Client sends file to /documents (multipart)
2. API Gateway authenticates and routes to Document Service
3. Document Service:
   a. Validates file type and size
   b. Runs virus scan (async)
   c. Uploads to S3
   d. Stores metadata in PostgreSQL
   e. Publishes event to Kafka
4. Worker Service picks up event:
   a. Generates thumbnail
   b. Extracts text for indexing
   c. Indexes in Elasticsearch
5. Notification Service sends upload confirmation
```

### Search Query Flow

```
1. Client sends search query to /search
2. API Gateway routes to Search Service
3. Search Service:
   a. Parses and enriches query
   b. Queries Elasticsearch
   c. Applies access control filters
   d. Formats and returns results
4. Results cached in Redis (5 min TTL)
```

## Scalability

### Horizontal Scaling

Each service can be scaled independently based on load:

| Service | Min Instances | Max Instances | Trigger |
|---------|---------------|---------------|---------|
| Auth | 2 | 10 | CPU > 70% |
| User | 2 | 8 | CPU > 70% |
| Document | 3 | 20 | Queue depth > 100 |
| Search | 2 | 15 | Latency > 200ms |
| Worker | 5 | 50 | Queue depth > 500 |

### Database Scaling

**PostgreSQL**:
- Primary + 2 read replicas
- Connection pooling (PgBouncer)
- Partitioning for large tables (documents, events)

**Redis**:
- Redis Cluster (6 nodes)
- Sentinel for high availability

**Elasticsearch**:
- 3-node cluster
- 1 replica per shard
- Hot-warm architecture for older data

## Security

### Authentication Layers

1. **API Gateway**: Token validation, rate limiting
2. **Service Level**: Permission checks
3. **Data Level**: Row-level security

### Data Encryption

- **At Rest**: AES-256 (S3, PostgreSQL)
- **In Transit**: TLS 1.3
- **Secrets**: HashiCorp Vault

### Security Headers

```
Strict-Transport-Security: max-age=31536000; includeSubDomains
Content-Security-Policy: default-src 'self'
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
```

## Monitoring & Observability

### Metrics (Prometheus)

- Request rate, latency, errors
- Resource utilization (CPU, memory, disk)
- Business metrics (users, documents, searches)

### Logging (ELK Stack)

- Structured JSON logs
- Correlation IDs for request tracing
- Log levels: DEBUG, INFO, WARN, ERROR

### Tracing (Jaeger)

- Distributed request tracing
- Service dependency mapping
- Latency analysis

### Alerting (PagerDuty)

| Alert | Condition | Severity |
|-------|-----------|----------|
| High Error Rate | > 5% errors | Critical |
| High Latency | p99 > 1s | Warning |
| Service Down | No heartbeat 1m | Critical |
| Disk Full | > 90% usage | Warning |

## Deployment

### Infrastructure (AWS)

- **Compute**: EKS (Kubernetes)
- **Database**: RDS (PostgreSQL), ElastiCache (Redis)
- **Search**: OpenSearch (managed Elasticsearch)
- **Storage**: S3 + CloudFront
- **Secrets**: Secrets Manager

### CI/CD Pipeline

```
Code Push → Build → Unit Tests → Docker Build → Integration Tests → 
Staging Deploy → E2E Tests → Production Deploy (Blue/Green)
```

### Environments

| Environment | Purpose | Data |
|-------------|---------|------|
| Development | Local development | Mock/seed data |
| Staging | Pre-production testing | Anonymized prod data |
| Production | Live system | Real data |

## Disaster Recovery

### Backup Strategy

- **Database**: Daily full backup, hourly WAL shipping
- **S3**: Cross-region replication
- **Elasticsearch**: Daily snapshots

### Recovery Objectives

- **RPO** (Recovery Point Objective): 1 hour
- **RTO** (Recovery Time Objective): 4 hours

### Failover Procedure

1. Detect failure (automated monitoring)
2. Promote read replica to primary
3. Update DNS/load balancer
4. Verify services operational
5. Investigate and fix original primary

---

*Architecture Version: 2.0*
*Last Updated: October 2024*
*Author: Platform Engineering Team*
