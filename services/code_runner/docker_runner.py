import docker
import tempfile
import os
import uuid

client = docker.from_env()

def run_python(code: str, timeout: int = 3) -> dict:
    job_id = str(uuid.uuid4())

    with tempfile.TemporaryDirectory() as tmpdir:
        code_path = os.path.join(tmpdir, "main.py")
        with open(code_path, "w") as f:
            f.write(code)

        try:
            container = client.containers.run(
                image="code-runner-python",
                command=["python", "main.py"],
                volumes={tmpdir: {"bind": "/code", "mode": "ro"}},
                working_dir="/code",
                network_disabled=True,
                mem_limit="128m",
                cpu_quota=50000,
                pids_limit=64,
                detach=True,
                stdout=True,
                stderr=True,
            )

            output = container.logs(stdout=True, stderr=True, timeout=timeout).decode()
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
