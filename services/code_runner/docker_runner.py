import docker
import os
import uuid

client = docker.from_env()

# Path inside this container where code files are written
CODE_EXECUTION_PATH = os.getenv("CODE_EXECUTION_PATH", "/tmp/code-execution")
# Named Docker volume used to share code files with sibling code-runner containers.
# When set, the spawned container mounts this volume instead of a host bind mount.
# Must match the actual Docker volume name (e.g. "bigoyu_code-execution").
CODE_VOLUME_NAME = os.getenv("CODE_VOLUME_NAME", "")

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

        # Use named volume if available (production), else fall back to bind mount (local dev)
        if CODE_VOLUME_NAME:
            volume_config = {
                CODE_VOLUME_NAME: {"bind": "/tmp/code-execution", "mode": "ro"}
            }
        else:
            volume_config = {
                CODE_EXECUTION_PATH: {"bind": "/tmp/code-execution", "mode": "ro"}
            }

        container = client.containers.run(
            image=config["image"],
            command=config["command"](job_id, config["extension"]),
            volumes=volume_config,
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
