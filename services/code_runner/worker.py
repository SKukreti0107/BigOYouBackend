from services.code_runner.docker_runner import run_code as execute_in_docker


def run_code(code:str,language:str):
    return execute_in_docker(code, language)