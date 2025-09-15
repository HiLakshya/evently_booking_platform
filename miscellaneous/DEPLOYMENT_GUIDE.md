# Deployment Guide

This guide describes the CI/CD pipeline and deployment process for the Evently Booking Platform using GitHub Actions, Docker Hub, and Render.

Live Swagger UI (production): [https://evently-booking-platform-latest.onrender.com/docs](https://evently-booking-platform-latest.onrender.com/docs)

## Table of Contents

- Overview
- Required GitHub Secrets
  - Docker Hub Credentials
  - Render Deployment
  - Application Environment Variables (Render)
- GitHub Actions Workflow
  - Triggers
  - Jobs and Steps
  - Workflow Configuration
  - Docker Image Details
- Render Deployment Process
  - Service Configuration
  - Deploy Hook Integration
  - Environment Variables
  - Deployment Flow
  - Service Features
- Complete Deployment Workflow
  - Initial Setup
  - Development Workflow
  - Monitoring Deployment
- Local Development
- Monitoring
- Troubleshooting
  - GitHub Actions
  - Docker Hub
  - Render
  - Debugging Commands
- Security Notes

## Required GitHub Secrets

Configure these secrets in the repository settings under Actions secrets and variables.

### Docker Hub Credentials

- `DOCKER_USERNAME`: Your Docker Hub username
- `DOCKER_PASSWORD`: Your Docker Hub password or access token

### Render Deployment

- `RENDER_DEPLOY_HOOK_URL`: Render deploy hook URL

### Application Environment Variables (Render)

Configure the following in the Render service environment (see `.env.example` for full list):

- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_URL`: Redis connection string
- `CELERY_BROKER_URL`: Celery broker URL (usually same as Redis)
- `CELERY_RESULT_BACKEND`: Celery result backend URL
- `SECRET_KEY`: Application secret key
- `ENVIRONMENT`: Set to `production`
- `PORT`: Port number (default: 3000)

## GitHub Actions Workflow

The workflow in `.github/workflows/deploy.yml` builds and publishes Docker images and triggers Render deployments.

### Triggers

- Push to `main`: build, push, and deploy
- Pull requests to `main`: build for validation (no push)

### Jobs and Steps

#### Pull Requests (`build-pr` job)

1. **Checkout Code**: Downloads the repository code
2. **Setup Docker Buildx**: Configures multi-platform Docker builds
3. **Build Docker Image**: Creates image with tag `temp/evently-booking-platform:pr-{PR_NUMBER}`
4. **Cache Management**: Uses GitHub Actions cache for faster builds

#### Main Branch (`build-and-push` job)

1. **Checkout Code**: Downloads the repository code
2. **Setup Docker Buildx**: Configures multi-platform Docker builds
3. **Docker Hub Login**: Authenticates using `DOCKER_USERNAME` and `DOCKER_PASSWORD` secrets
4. **Extract Metadata**: Generates image tags:
   - `{DOCKER_USERNAME}/evently-booking-platform:latest`
   - `{DOCKER_USERNAME}/evently-booking-platform:main-{COMMIT_SHA}`
5. **Build and Push**: Creates multi-platform image and pushes to Docker Hub
6. **Cache Management**: Uses GitHub Actions cache for faster builds

### Workflow Configuration

```yaml
# Key workflow settings
env:
  REGISTRY: docker.io
  IMAGE_NAME: evently-booking-platform

# Triggers
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
```

### Docker Image Details

- **Base Image**: `python:3.12-slim`
- **Multi-stage Build**: Optimized for production
- **Security**: Runs as non-root user
- **Health Check**: Built-in health monitoring
- **Platforms**: `linux/amd64` (extensible to ARM64)

## Docker Images

### Production Image Tags

- `your-username/evently-booking-platform:latest` - Latest main branch
- `your-username/evently-booking-platform:main-<sha>` - Specific commit

## Render Deployment Process

### Render Service Configuration

#### 1. Service Setup

1. **Service Type**: Web Service
2. **Runtime**: Docker
3. **Docker Image**: `{DOCKER_USERNAME}/evently-booking-platform:latest`
4. **Port**: 3000
5. **Health Check Path**: `/health`

#### 2. Deploy Hook Integration

1. **Create Deploy Hook**: In Render dashboard, create a deploy hook
2. **Copy Hook URL**: Save the deploy hook URL
3. **Add to GitHub Secrets**: Store as `RENDER_DEPLOY_HOOK_URL`

#### 3. Environment Variables (Render Dashboard)

Configure these in your Render service environment (see `.env.example` for reference):

```env
DATABASE_URL=postgresql://user:password@host:5432/database
REDIS_URL=redis://host:6379/0
CELERY_BROKER_URL=redis://host:6379/1
CELERY_RESULT_BACKEND=redis://host:6379/2
SECRET_KEY=your-production-secret-key
ENVIRONMENT=production
PORT=3000
```

### Deployment Flow

#### Automatic Deployment (recommended)

1. **Code Push**: Developer pushes to `main` branch
2. **GitHub Actions**: Workflow triggers automatically
3. **Docker Build**: Image built and pushed to Docker Hub
4. **Render Deploy**: Service automatically pulls new image
5. **Health Check**: Render verifies service health

#### Manual Deployment

1. **Trigger Deploy Hook**: Use the deploy hook URL to trigger deployment
2. **Image Pull**: Render pulls the latest `latest` tag from Docker Hub
3. **Service Restart**: Application restarts with new image

### Render Service Features

- **Auto-scaling**: Automatically scales based on traffic
- **Health Monitoring**: Continuous health checks
- **Log Management**: Centralized logging
- **SSL/TLS**: Automatic HTTPS certificates
- **Custom Domains**: Support for custom domain names

## Complete Deployment Workflow

### Step-by-Step Process

#### 1. Initial Setup

```bash
# 1. Fork/clone the repository
git clone https://github.com/your-username/evently-booking-platform.git
cd evently-booking-platform

# 2. Set up GitHub Secrets
# Go to Settings > Secrets and variables > Actions
# Add: DOCKER_USERNAME, DOCKER_PASSWORD, RENDER_DEPLOY_HOOK_URL

# 3. Configure Render service
# Create new Web Service in Render dashboard
# Set Docker image: your-username/evently-booking-platform:latest
# Configure environment variables
```

#### 2. Development Workflow

```bash
# 1. Make changes locally
git add .
git commit -m "feat: add new feature"

# 2. Push to main branch
git push origin main

# 3. GitHub Actions automatically:
#    - Builds Docker image
#    - Pushes to Docker Hub
#    - Triggers Render deployment

# 4. Render automatically:
#    - Pulls new image
#    - Restarts service
#    - Verifies health
```

#### 3. Monitoring Deployment

- **GitHub Actions**: Check workflow status in Actions tab
- **Docker Hub**: Verify image was pushed successfully
- **Render Dashboard**: Monitor deployment logs and health
- **Application**: Test endpoints at your Render URL

## Local Development

### Build and Run

```bash
# Development with hot reload
docker-compose up

# Production build
docker-compose -f docker-compose.prod.yml up

# Build specific image
docker build -t evently-booking-platform:local .
```

## Monitoring

### Health Checks

- Application: `http://localhost:3000/health`
- Docker health check runs every 30 seconds
- Render monitors service health automatically

### Logs

- View logs in Render dashboard
- Use `docker logs` for local debugging

## Troubleshooting

### GitHub Actions

#### Build Failures

1. **Check Workflow Logs**: Go to Actions tab in GitHub repository
2. **Verify Secrets**: Ensure `DOCKER_USERNAME`, `DOCKER_PASSWORD` are set
3. **Dockerfile Issues**: Check for syntax errors in Dockerfile
4. **Dependencies**: Verify all dependencies are properly specified in pyproject.toml

#### Common Build Errors

```bash
# Docker login failed
Error: Cannot perform an interactive login from a non TTY device
# Solution: Check DOCKER_PASSWORD secret is valid

# Build context issues
Error: failed to solve: failed to compute cache key
# Solution: Check .dockerignore file and build context

# Multi-platform build issues
Error: failed to solve: no match for platform
# Solution: Verify platform specification in workflow
```

### Docker Hub

#### Push Failures

1. **Authentication**: Verify Docker Hub credentials
2. **Repository Access**: Ensure repository exists and is accessible
3. **Image Size**: Check if image exceeds Docker Hub limits
4. **Rate Limits**: Monitor Docker Hub pull/push rate limits

### Render

#### Service will not start

1. **Image Pull**: Check if image exists in Docker Hub
2. **Environment Variables**: Verify all required env vars are set
3. **Port Configuration**: Ensure PORT=3000 is set
4. **Health Check**: Verify `/health` endpoint responds correctly

#### Service unhealthy

1. **Database Connection**: Check DATABASE_URL format and connectivity
2. **Redis Connection**: Verify REDIS_URL is accessible
3. **Dependencies**: Ensure all required services are available
4. **Logs**: Check Render service logs for specific errors

#### Common Render Errors

```bash
# Database connection failed
Error: could not connect to server
# Solution: Check DATABASE_URL format and database availability

# Redis connection failed
Error: Redis connection refused
# Solution: Verify REDIS_URL and Redis service status

# Health check failed
Error: Health check failed
# Solution: Ensure /health endpoint returns 200 status
```

### Debugging Commands

#### Local Testing

```bash
# Test Docker build locally
docker build -t evently-booking-platform:test .

# Test with environment variables
docker run -e DATABASE_URL=... -e REDIS_URL=... evently-booking-platform:test

# Check container logs
docker logs <container_id>

# Test health endpoint
curl http://localhost:3000/health
```

#### Production Debugging

```bash
# Check Render service logs
# Use Render dashboard or CLI

# Test database connectivity
# Use database client or connection string

# Verify environment variables
# Check Render service environment settings
```

## GitHub Actions Workflow Details

### Workflow File: `.github/workflows/deploy.yml`

The complete workflow configuration includes:

#### Environment Variables

```yaml
env:
  REGISTRY: docker.io
  IMAGE_NAME: evently-booking-platform
```

#### Job Configuration

- **build-pr**: Runs on pull requests, builds image for testing
- **build-and-push**: Runs on main branch pushes, builds and pushes to Docker Hub

#### Key Features

- **Multi-platform builds**: Supports AMD64 architecture
- **Caching**: Uses GitHub Actions cache for faster builds
- **Metadata extraction**: Automatically generates appropriate tags
- **Security**: Uses secrets for authentication

#### Workflow Triggers

```yaml
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
```

### Workflow Steps Breakdown

#### 1. Checkout Code

```yaml
- name: Checkout code
  uses: actions/checkout@v4
```

#### 2. Set up Docker Buildx

```yaml
- name: Set up Docker Buildx
  uses: docker/setup-buildx-action@v3
```

#### 3. Docker Hub Authentication (main branch only)

```yaml
- name: Log in to Docker Hub
  uses: docker/login-action@v3
  with:
    username: ${{ secrets.DOCKER_USERNAME }}
    password: ${{ secrets.DOCKER_PASSWORD }}
```

#### 4. Extract Metadata (main branch only)

```yaml
- name: Extract metadata
  id: meta
  uses: docker/metadata-action@v5
  with:
    images: ${{ secrets.DOCKER_USERNAME }}/${{ env.IMAGE_NAME }}
    tags: |
      type=raw,value=latest
      type=sha,prefix=main-
```

#### 5. Build and Push

```yaml
- name: Build and push Docker image
  uses: docker/build-push-action@v5
  with:
    context: .
    file: ./Dockerfile
    push: true
    tags: ${{ steps.meta.outputs.tags }}
    labels: ${{ steps.meta.outputs.labels }}
    cache-from: type=gha
    cache-to: type=gha,mode=max
    platforms: linux/amd64
```

## Security Notes

- **Non-root User**: Docker container runs as non-root user for security
- **Secrets Management**: All sensitive data managed through GitHub Secrets
- **Multi-stage Build**: Reduces image size and attack surface
- **Health Checks**: Built-in health monitoring ensures service reliability
- **Dependency Scanning**: Regular security updates through dependency management
- **Image Scanning**: Docker Hub provides vulnerability scanning for pushed images
