import docker
import os
import uuid

client = docker.from_env()

# Use a shared volume path that's accessible by the host Docker daemon
CODE_EXECUTION_PATH = "/tmp/code-execution"
DOCKER_VOLUME_NAME = os.getenv("DOCKER_VOLUME_NAME","backend_code-execution")

LANGUAGE_CONFIGS = {
    "python": {
        "image": "code-runner-python",
        "extension": "py",
        "command": lambda job_id, ext: ["python", f"/tmp/code-execution/{job_id}/main.{ext}"]
    },
    "cpp": {
        "image": "code-runner-cpp",
        "extension": "cpp",
        "command": lambda job_id, ext: ["sh", "-c", f"g++ /tmp/code-execution/{job_id}/main.{ext} -o /tmp/main && /tmp/main"]
    },
    "java": {
        "image": "code-runner-java",
        "extension": "java",
        "filename": "Solution.java",
        "command": lambda job_id, ext: ["sh", "-c", f"javac /tmp/code-execution/{job_id}/Solution.{ext} -d /tmp && java -cp /tmp Solution"]
    }
}

def run_code(code: str, language: str, timeout: int = 5) -> dict:
    if language not in LANGUAGE_CONFIGS:
        return {"status": "error", "output": f"Unsupported language: {language}"}

    config = LANGUAGE_CONFIGS[language]
    job_id = str(uuid.uuid4())
    job_dir = os.path.join(CODE_EXECUTION_PATH, job_id)
    os.makedirs(job_dir, exist_ok=True)

    filename = config.get("filename", f"main.{config['extension']}")
    code_path = os.path.join(job_dir, filename)

    try:
        with open(code_path, "w") as f:
            f.write(code)

        container = client.containers.run(
            image=config["image"],
            command=config["command"](job_id, config["extension"]),
            volumes={
                DOCKER_VOLUME_NAME: {"bind": "/tmp/code-execution", "mode": "ro"}
            },
            network_disabled=True,
            mem_limit="128m",
            cpu_quota=50000,
            pids_limit=64,
            detach=True,
            stdout=True,
            stderr=True,
        )

        try:
            # Wait for container to finish with specific timeout
            container.wait(timeout=timeout)
        except Exception:
            container.kill()
            return {"status": "error", "output": "Time Limit Exceeded"}

        output = container.logs(stdout=True, stderr=True).decode()
        container.remove(force=True)

        return {
            "status": "success",
            "output": output
        }

    except Exception as e:
        return {
            "status": "error",
            "output": str(e)
        }
    finally:
        # Cleanup
        try:
            if os.path.exists(code_path):
                os.remove(code_path)
            if os.path.exists(job_dir):
                os.rmdir(job_dir)
        except:
            pass

def run_python(code: str, timeout: int = 3) -> dict:
    return run_code(code, "python", timeout)

def run_cpp(code: str, timeout: int = 3) -> dict:
    return run_code(code, "cpp", timeout)

def run_java(code: str, timeout: int = 3) -> dict:
    return run_code(code, "java", timeout)
