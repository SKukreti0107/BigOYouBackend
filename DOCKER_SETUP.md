# Setup Instructions

## Building and Running

### 1. Build the code-runner-python image
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
- **Shared Volume**: `/tmp/code-execution` allows the backend to write code files that spawned containers can access

## Important Notes

- The Docker socket is mounted to allow spawning sibling containers
- Code execution happens in isolated, resource-limited containers
- Temporary files are cleaned up after execution
