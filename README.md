# Evently Booking Platform

Evently is a production-grade event booking backend built with FastAPI and PostgreSQL. It is designed for high concurrency, seat-level inventory, and real-time analytics.

[![Watch the video](https://img.youtube.com/vi/TLd7vTm1N3c/0.jpg)](https://www.youtube.com/watch?v=TLd7vTm1N3c)

Note: This project originated as a solution to the Evently Challenge by [@atlanhq](https://github.com/atlanhq).

## Table of Contents

- Introduction
- Features
- Architecture and Technology
- Getting Started
  - Prerequisites
  - Installation
  - Configuration
  - Running Locally
  - Docker
- API Documentation
- Documentation Index
- Project Structure
- Development
- Testing
- Deployment
- Security
- License

## Introduction

Evently implements a robust booking workflow with concurrency control to prevent overselling, including optimistic locking, distributed seat holds, and atomic capacity updates. It also provides an admin surface for event management and analytics.

## Features

- High-concurrency booking with optimistic locking and distributed locking
- Real-time availability with Redis-backed caches and seat holds
- User authentication and authorization with JWT
- Admin event management (create, update, archive)
- Waitlist with notifications when capacity frees up
- Analytics endpoints for revenue and utilization
- Seat selection and dynamic pricing (optional modules)
- Email notifications for key booking lifecycle events

## Architecture and Technology

- Backend: FastAPI (Python 3.12+)
- Database: PostgreSQL with SQLAlchemy ORM
- Caching and Locks: Redis
- Background Jobs: Celery
- Authentication: JWT (bcrypt for password hashing)
- Tooling: pytest, coverage, Black, MyPy, pre-commit

For the ER diagram and high-level system design, see the [System Design](miscellaneous/DESIGN.md) document.

## Getting Started

### Prerequisites

- Python 3.12+
- uv (package manager): see [uv](https://docs.astral.sh/uv/)
- PostgreSQL
- Redis

### Installation

```bash
git clone <repo-url>
cd evently-booking-platform
uv sync
```

### Configuration

Copy the example environment and fill required values:

```bash
cp .env.example .env
```

Required variables (see `.env.example` for the full list):

- DATABASE_URL
- REDIS_URL
- SECRET_KEY
- CELERY_BROKER_URL
- CELERY_RESULT_BACKEND
- SMTP_USERNAME, SMTP_PASSWORD (for email)

### Running Locally

```bash
uv run uvicorn evently_booking_platform.main:app --host 0.0.0.0 --port 3000 --reload
```

API documentation:

- Swagger: [http://localhost:3000/docs](http://localhost:3000/docs)
- ReDoc: [http://localhost:3000/redoc](http://localhost:3000/redoc)

### Docker

Development with hot reload:

```bash
docker-compose up
```

Production build:

```bash
docker-compose -f docker-compose.prod.yml up
```

## API Documentation

See the full reference in [API Documentation](miscellaneous/API_DOCUMENTATION.md).

Live Swagger UI (production): [https://evently-booking-platform-latest.onrender.com/docs](https://evently-booking-platform-latest.onrender.com/docs)

## Documentation Index

- [Implementation Plan](miscellaneous/IMPLEMENTATION_PLAN.md)
- [Admin Authentication Guide](miscellaneous/ADMIN_AUTHENTICATION_GUIDE.md)
- [API Documentation](miscellaneous/API_DOCUMENTATION.md)
- [Advanced Features](miscellaneous/ADVANCED_FEATURES_DOCUMENTATION.md)
- [System Design](miscellaneous/DESIGN.md)
- [Deployment Guide](miscellaneous/DEPLOYMENT_GUIDE.md)
- [External Project Notes (Google Doc)](https://docs.google.com/document/d/1U9_g87hdF3OtrGSYCXIQFcho26UjMy5P/edit)

## Project Structure

```
evently-booking-platform/
├── evently_booking_platform/   # Core app (APIs, models, services, schemas, utils)
├── tests/                      # Unit and integration tests
├── scripts.py                  # Development scripts
├── miscellaneous/              # Documentation and guides
│   ├── IMPLEMENTATION_PLAN.md
│   ├── ADMIN_AUTHENTICATION_GUIDE.md
│   ├── API_DOCUMENTATION.md
│   ├── ADVANCED_FEATURES_DOCUMENTATION.md
│   ├── DESIGN.md
│   └── DEPLOYMENT_GUIDE.md
```

## Development

Common commands:

```bash
python scripts.py start
```

## Testing

Planned test suites include unit, integration, and load testing. See `miscellaneous/IMPLEMENTATION_PLAN.md` for scope.

## Deployment

Continuous delivery is provided via GitHub Actions with Docker images published to Docker Hub and automated rollouts on Render. See `miscellaneous/DEPLOYMENT_GUIDE.md` for details.

## Security

- Run the container as a non-root user
- Keep secrets in environment variables or secret managers
- JWT tokens are short-lived by default

## License

MIT. See `LICENSE`.

## Demo

- Video: [https://youtu.be/TLd7vTm1N3c](https://youtu.be/TLd7vTm1N3c)
- Live: [https://evently-booking-platform-latest.onrender.com/](https://evently-booking-platform-latest.onrender.com/)
