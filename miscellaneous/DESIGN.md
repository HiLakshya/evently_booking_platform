# System Design

This document describes the architecture, design principles, and data modeling for the Evently Booking Platform.

Live Swagger UI (production): https://evently-booking-platform-latest.onrender.com/docs

---

## Design Principles

- **Concurrency Safety** – Optimistic locking, row-level transactions, Redis locks.
- **Scalability** – Horizontal scaling with load balancers + DB connection pooling.
- **Performance** – Redis caching, async operations, efficient indexing.
- **Reliability** – Circuit breakers, retry strategies, background task queues.
- **Separation of Concerns** – Clear modular structure (users, bookings, events, analytics).

---

## High-level Architecture

```mermaid
graph TB

  subgraph "Client Layer"
    WEB[Web Frontend]
    API_CLIENT[Mobile/API Clients]
  end

  subgraph "Load Balancer"
    LB[Load Balancer / Nginx]
  end

  subgraph "Application Layer"
    APP1[FastAPI App Instance 1]
    APP2[FastAPI App Instance 2]
    APPN[FastAPI App Instance N]
  end

  subgraph "Caching Layer"
    REDIS[Redis - cache & locks]
  end

  subgraph "Database Layer"
    PG_PRIMARY[(PostgreSQL Primary)]
    PG_REPLICA[(PostgreSQL Replica)]
  end

  subgraph "Background Workers"
    CELERY[Celery Workers]
    SCHEDULER[Task Scheduler]
  end

  subgraph "External Services"
    EMAIL[Email Notifications]
    MONITORING[Monitoring & Logging]
  end

  WEB --> LB
  API_CLIENT --> LB
  LB --> APP1
  LB --> APP2
  LB --> APPN

  APP1 --> REDIS
  APP2 --> REDIS
  APPN --> REDIS

  APP1 --> PG_PRIMARY
  APP2 --> PG_PRIMARY
  APPN --> PG_PRIMARY

  APP1 --> PG_REPLICA
  APP2 --> PG_REPLICA
  APPN --> PG_REPLICA

  APP1 --> CELERY
  APP2 --> CELERY
  APPN --> CELERY

  CELERY --> EMAIL
  CELERY --> PG_PRIMARY
  SCHEDULER --> CELERY

```

---

## Concurrency Control Strategy

1. **Database-level**

   - Row-level locking on event capacity.
   - Optimistic locking (version fields).
   - Serializable transactions for critical updates.

2. **Application-level**

   - Redis distributed locks for seat holds.
   - Async request handling for non-blocking I/O.
   - Circuit breakers for external services.

3. **Booking flow**

   - Temporary seat holds with TTL.
   - Atomic booking operations.
   - Compensation for failed transactions.

---

## Core Services

- **Event Service** → CRUD for events, search, filtering, capacity.
- **Booking Service** → Create/cancel bookings, manage waitlist, concurrency safety.
- **User Service** → Registration, login (JWT), profiles.
- **Analytics Service** → Reports, dashboards, advanced trends.
- **Notification Service** → Emails for bookings, cancellations, waitlist spots.

---

## Entity Relationship Diagram (ERD)

```mermaid
erDiagram

  USERS {
    uuid id PK
    string email UK
    string password_hash
    string first_name
    string last_name
    boolean is_admin
    boolean is_active
    timestamp created_at
    timestamp updated_at
  }

  EVENTS {
    uuid id PK
    string name
    text description
    string venue
    timestamp event_date
    int total_capacity
    int available_capacity
    decimal price
    boolean has_seat_selection
    int version
    timestamp created_at
    timestamp updated_at
  }

  BOOKINGS {
    uuid id PK
    uuid user_id FK
    uuid event_id FK
    int quantity
    decimal total_amount
    enum status
    timestamp created_at
    timestamp updated_at
    timestamp expires_at
  }

  SEATS {
    uuid id PK
    uuid event_id FK
    string section
    string row
    string number
    decimal price
    enum status
    timestamp created_at
    timestamp updated_at
  }

  SEAT_BOOKINGS {
    uuid id PK
    uuid booking_id FK
    uuid seat_id FK
    timestamp created_at
  }

  WAITLIST {
    uuid id PK
    uuid user_id FK
    uuid event_id FK
    int requested_quantity
    int position
    enum status
    timestamp created_at
  }

  BOOKING_HISTORY {
    uuid id PK
    uuid booking_id FK
    enum action
    text details
    timestamp created_at
  }

  USERS ||--o{ BOOKINGS : makes
  EVENTS ||--o{ BOOKINGS : has
  EVENTS ||--o{ SEATS : contains
  BOOKINGS ||--o{ SEAT_BOOKINGS : includes
  SEATS ||--o{ SEAT_BOOKINGS : reserved_by
  USERS ||--o{ WAITLIST : joins
  EVENTS ||--o{ WAITLIST : has
  BOOKINGS ||--o{ BOOKING_HISTORY : tracks
```

---

## Error Handling Strategy

- **Concurrency Errors** → Retry with exponential backoff.
- **Business Logic Errors** → Validation errors with descriptive messages.
- **System Errors** → Circuit breakers, fallback responses.
- **Rate Limiting** → Headers `X-RateLimit-*`.

---

## Monitoring and Observability

**Metrics tracked**

- Booking success rate, cancellation rate, revenue.
- Response times (p50, p95, p99).
- Database connection pool health.
- Cache hit/miss ratios.

**Alerting**

- Critical: booking failures, DB down.
- Warning: high latency, cache misses.
- Business: unusual booking patterns.

---

This design aims to ensure correctness, scalability, and performance under heavy traffic.
