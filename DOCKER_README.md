# Docker Setup for Evently Booking Platform

This guide explains how to build and run the Evently Booking Platform using Docker.

## Prerequisites

- Docker Desktop installed and running
- Docker Compose installed
- Git (for cloning the repository)

## Quick Start

### Development Environment

1. **Start the development environment:**

   ```bash
   docker-compose up --build
   ```

2. **Access the application:**

   - API: http://localhost:3000
   - API Documentation: http://localhost:3000/docs
   - Database: localhost:5432
   - Redis: localhost:6379

3. **Stop the environment:**
   ```bash
   docker-compose down
   ```

### Production Environment

1. **Create environment file:**

   ```bash
   cp .env.example .env
   # Edit .env with your production values
   ```

2. **Start production environment:**
   ```bash
   docker-compose -f docker-compose.prod.yml up --build
   ```

## Docker Files

### Dockerfile

- **Purpose**: Production-ready multi-stage build
- **Features**:
  - Optimized for size and security
  - Non-root user execution
  - Health checks
  - Virtual environment isolation

### Dockerfile.dev

- **Purpose**: Development environment
- **Features**:
  - Hot reload support
  - Development dependencies
  - Volume mounting for live code changes

### docker-compose.yml

- **Purpose**: Development environment with all services
- **Services**:
  - `app`: Main FastAPI application
  - `celery-worker`: Background task processor
  - `celery-beat`: Scheduled task scheduler
  - `db`: PostgreSQL database
  - `redis`: Redis cache and message broker

### docker-compose.prod.yml

- **Purpose**: Production environment
- **Services**: Same as development but without database and Redis (expects external services)

## Building Images

### Build Production Image

```bash
docker build -t evently-booking-platform:latest .
```

### Build Development Image

```bash
docker build -f Dockerfile.dev -t evently-booking-platform:dev .
```

### Build and Push to Registry

```bash
# Build
docker build -t your-registry/evently-booking-platform:latest .

# Push
docker push your-registry/evently-booking-platform:latest
```

## Environment Variables

Copy `.env.example` to `.env` and configure your values:

```bash
cp .env.example .env
# Edit .env with your actual values
```

**Required variables** (see `.env.example` for complete list):

```env
# Database
DATABASE_URL=postgresql://user:password@db:5432/evently

# Redis
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2

# Security
SECRET_KEY=your-secret-key-here

# Environment
ENVIRONMENT=development
```

## Common Commands

### Development

```bash
# Start all services
docker-compose up

# Start in background
docker-compose up -d

# View logs
docker-compose logs -f app

# Rebuild and start
docker-compose up --build

# Stop all services
docker-compose down

# Remove volumes (careful!)
docker-compose down -v
```

### Production

```bash
# Start production services
docker-compose -f docker-compose.prod.yml up -d

# View logs
docker-compose -f docker-compose.prod.yml logs -f

# Stop production services
docker-compose -f docker-compose.prod.yml down
```

### Database Operations

```bash
# Run database migrations
docker-compose exec app alembic upgrade head

# Create new migration
docker-compose exec app alembic revision --autogenerate -m "description"

# Access database shell
docker-compose exec db psql -U user -d evently
```

### Debugging

```bash
# Access container shell
docker-compose exec app bash

# View container logs
docker logs <container_id>

# Check container status
docker ps

# Inspect container
docker inspect <container_id>
```

## Troubleshooting

### Common Issues

1. **Port already in use:**

   ```bash
   # Check what's using the port
   netstat -tulpn | grep :3000

   # Kill the process or change port in docker-compose.yml
   ```

2. **Database connection issues:**

   - Ensure PostgreSQL is running
   - Check DATABASE_URL format
   - Verify network connectivity between containers

3. **Permission issues:**

   ```bash
   # Fix file permissions
   sudo chown -R $USER:$USER .
   ```

4. **Build failures:**

   ```bash
   # Clean Docker cache
   docker system prune -a

   # Rebuild without cache
   docker-compose build --no-cache
   ```

### Health Checks

The application includes health check endpoints:

- **Basic health**: `GET /health`
- **Detailed health**: `GET /health/detailed`
- **Metrics**: `GET /metrics`

### Monitoring

Monitor your containers:

```bash
# Resource usage
docker stats

# Container health
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Logs with timestamps
docker-compose logs -f --timestamps
```

## Security Considerations

1. **Never commit `.env` files** with real credentials
2. **Use secrets management** in production
3. **Regularly update base images** for security patches
4. **Run containers as non-root** (already configured)
5. **Use specific image tags** instead of `latest`

## Performance Optimization

1. **Multi-stage builds** reduce final image size
2. **Layer caching** speeds up rebuilds
3. **Volume mounting** for development efficiency
4. **Resource limits** prevent container resource exhaustion

## CI/CD Integration

The project includes GitHub Actions workflow for automated building and pushing:

- **Triggers**: Push to main branch, Pull requests
- **Actions**: Build, test, and push to Docker Hub
- **Secrets required**: `DOCKER_USERNAME`, `DOCKER_PASSWORD`

## Support

For issues related to Docker setup:

1. Check the logs: `docker-compose logs`
2. Verify environment variables
3. Ensure all required services are running
4. Check network connectivity between containers

## Additional Resources

- [Docker Documentation](https://docs.docker.com/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [FastAPI Docker Guide](https://fastapi.tiangolo.com/deployment/docker/)
