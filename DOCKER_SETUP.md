# Setup Instructions

## Building and Running

### 1. Build the code-runner images
```bash
docker build -t code-runner-python ./services/code_runner/images/python
docker build -t code-runner-cpp ./services/code_runner/images/cpp
docker build -t code-runner-java ./services/code_runner/images/java
```

### 2. Start the services
```bash
docker-compose up --build
```

This will start:
- Redis (on port 6379)
- FastAPI backend (on port 8000)
- RQ worker (processing code_queue)

### 3. Test the setup
```bash
curl -X POST http://localhost:8000/execute \
  -H "Content-Type: application/json" \
  -d '{"language": "python", "code": "print(\"Hello World\")"}'
```

## Architecture

- **Backend Container**: Runs FastAPI + RQ worker, has access to host Docker daemon via socket mount
- **Redis Container**: Manages job queue
- **Code Runner**: Spawned as sibling containers by the backend
- **Shared Volume**: A named Docker volume (`bigoyu_code-execution`) is shared between the worker and spawned code-runner containers to pass code files

## Volume Sharing (Important for Production)

Code execution uses **sibling containers** — the worker spawns code-runner containers via the host Docker socket. For the worker and code-runner to share files:

- A **named Docker volume** (`code-execution`) is used instead of host bind mounts.
- The compose project is named `bigoyu` (set in `docker-compose.yml`), so Docker creates the volume as `bigoyu_code-execution`.
- The `CODE_VOLUME_NAME` environment variable tells `docker_runner.py` which named volume to mount into spawned code-runner containers.
- This ensures files written by the worker are visible to code-runner containers on **any host** (local, cloud VM, etc.).

> **If you change the project name** in `docker-compose.yml`, update the `CODE_VOLUME_NAME` env var to match: `<project-name>_code-execution`.

### Verifying the volume
```bash
docker volume ls | grep code-execution
# Should show: bigoyu_code-execution
```

## Important Notes

- The Docker socket is mounted to allow spawning sibling containers
- Code execution happens in isolated, resource-limited containers
- Temporary files are cleaned up after execution

## Troubleshooting

### "No such file or directory" when running code
This means the code-runner container can't see the files written by the worker. Check:
1. `docker volume ls` — the volume `bigoyu_code-execution` must exist
2. `CODE_VOLUME_NAME` env var must match the actual volume name
3. If you changed the compose project name, update `CODE_VOLUME_NAME` accordingly
4. Run `docker-compose down -v` and `docker-compose up --build` to recreate volumes
