# Vault 3000 Terminal Agent - Docker Setup

This repository contains Docker setup files to run the Vault 3000 terminal AI agent in a containerized environment with SSH access.

## Files Included

- `Dockerfile` - Docker container configuration
- `docker-compose.yml` - Container orchestration
- `entrypoint.sh` - Container startup script
- `.dockerignore` - Docker build exclusions

## Features

- SSH server for remote access
- Python virtual environment with all dependencies
- Volume mounts for configuration files
- Bash aliases setup (ag, ask, prom)
- Complete term_agent environment

## Quick Start

### Prerequisites

- Docker installed on your system
- Docker Compose installed
- Your `.env` file with API keys (copy from .env.copy and fill in your keys)

### 1. Setup Environment

```bash
# Copy and configure your .env file
cp .env.copy .env
# Edit .env with your API keys (OpenAI, Google, etc.)
```

### 2. Use Pre-built Image from GitHub Container Registry

The project includes GitHub Actions CI/CD pipeline that automatically builds and pushes Docker images to GHCR (GitHub Container Registry).

```bash
docker pull ghcr.io/noxgle/term_agent:latest
docker run -d \
  --name term-agent-container \
  -p 2222:22 \
  -v $(pwd)/.env:/app/.env:ro \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/goal:/app/goal \
  -v $(pwd)/prompt:/app/prompt \
  -e TZ=Europe/Warsaw \
  --restart unless-stopped \
  -it \
  ghcr.io/noxgle/term_agent:latest
```

### Alternative: Build Locally

```bash
# Build the container locally
docker-compose build
docker-compose up -d
```

### 3. Connect via SSH

```bash
# Connect to the container
ssh root@localhost -p 2222

# Password: 123456 (change this in production)
```

## Usage

Once connected via SSH, you can use the Vault 3000 commands:

```bash
# Start the AI agent
ag

# Start chat mode
ask

# Start prompt creator
prom
```

## Environment Variables

Create a `.env` file with your API keys:

```env
AI_ENGINE=ollama 

OPENAI_API_KEY=openai_api_key_here
OPENAI_MODEL=gpt-4o-mini
OPENAI_TEMPERATURE=0.5
OPENAI_MAX_TOKENS=1000
OLLAMA_URL=http://192.168.200.202:11434/api/generate

# granite3.3:8b,gemma3:12b,cogito:8b,qwen3:8b
OLLAMA_MODEL=cogito:8b
OLLAMA_TEMPERATURE=0.5

# gemini-2.5-pro-exp-03-25,gemini-2.0-flash
GOOGLE_MODEL=gemini-2.5-flash-preview-05-20
GOOGLE_API_KEY=google_api_key_here

SSH_REMOTE_TIMEOUT=360
AUTO_ACCEPT=false

 # poziom logowania: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_LEVEL=DEBUG         
LOG_FILE=app.log      
LOG_TO_CONSOLE=false
```

## Container Configuration

### Ports

- **22** (SSH) mapped to host port **2222**

### Volumes

- `./.env` → `/app/.env` (read-only)
- `./logs` → `/app/logs`
- `./goal` → `/app/goal`
- `./prompt` → `/app/prompt`

## Management Commands

```bash
# View container status
docker-compose ps

# View logs
docker-compose logs -f

# Stop container
docker-compose down

# Rebuild container
docker-compose up -d --build

# Enter running container
docker exec -it term-agent-container /bin/bash
```

## Security Notes

⚠️ **Production Use:**
- Change the default SSH password (123456) in the Dockerfile
- Consider using SSH keys instead of password authentication
- The .ssh directory is excluded from Docker build to prevent permission issues

## Troubleshooting

### Common Issues

1. **SSH connection refused**
   - Ensure port 2222 is not blocked by firewall
   - Wait a few seconds for the container to start

2. **No .env file found**
   - Mount .env file: `docker run -v $(pwd)/.env:/app/.env ...`
   - Or use docker-compose which mounts it automatically

3. **Permission denied**
   - Ensure .env file permissions allow container read access
   - SSH uses password authentication by default

### Debug Commands

```bash
# Check container environment
docker exec -it term-agent-container env

# View SSH logs
docker exec -it term-agent-container tail -f /var/log/auth.log

# Test Python environment
docker exec -it term-agent-container /app/.venv/bin/python --version
```

## Advanced Usage

### Custom SSH Port

Edit docker-compose.yml:

```yaml
ports:
  - "2223:22"  # Change host port to 2223
```

### Multiple Containers

Run multiple instances:

```yaml
version: '3.8'
services:
  term-agent-1:
    build: .
    ports:
      - "2222:22"
    # ... other config

  term-agent-2:
    build: .
    ports:
      - "2223:22"
    # ... other config
```

### Docker Swarm

```bash
# Deploy to swarm
docker stack deploy -c docker-compose.yml vault3000
```

### Accessing Built Images

Images are published to: `ghcr.io/noxgle/term_agent` with tags:
- `latest` - Latest main branch build
- `v1.0.0`, `v1.1.0`, etc. - Version releases

### Manual Trigger

Workflow can be triggered manually from GitHub Actions tab if needed.

## License

Same as term_agent repository.
