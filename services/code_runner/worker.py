from services.code_runner.docker_runner import run_python


def run_code(code:str,language:str):
    if language == "python":
        return run_python(code)
    
    return {
        "status": "error",
        "output": f"Unsupported language: {language}"
    }