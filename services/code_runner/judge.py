import os
import base64
import json
import httpx
from typing import Optional, List, Dict, Any

JUDGE0_URL = os.getenv("JUDGE0_URL", "http://localhost:2358").rstrip("/")

# Language mappings to Judge0 IDs:
# Python 3: 71
# C++ (GCC 9.2.0): 75 (or 54 depending on compiler version; 75 is typical C++17)
# Java (OpenJDK 13.0.1): 62
JUDGE0_LANG_IDS = {
    "python": 71,
    "python3": 71,
    "cpp": 75,
    "java": 62
}

def b64_encode(s: str) -> str:
    if not s:
        return ""
    return base64.b64encode(s.encode("utf-8")).decode("utf-8")

def b64_decode(s: str) -> str:
    if not s:
        return ""
    try:
        return base64.b64decode(s.encode("utf-8")).decode("utf-8")
    except Exception:
        return s

def submit_to_judge0(code: str, language: str, expected_output: Optional[str] = None) -> Dict[str, Any]:
    """
    Submits wrapped source code to Judge0, blocks until execution finishes, and returns the result.
    Falls back to local Docker execution if Judge0 is offline or experiences sandboxing/cgroup errors.
    """
    from services.code_runner.docker_runner import run_code as local_run_code

    lang_id = JUDGE0_LANG_IDS.get(language.lower())
    if not lang_id:
        return {
            "status": "error",
            "error_detail": f"Unsupported language: {language}"
        }

    payload = {
        "source_code": b64_encode(code),
        "language_id": lang_id
    }
    if expected_output is not None:
        payload["expected_output"] = b64_encode(expected_output)

    url = f"{JUDGE0_URL}/submissions?base64_encoded=true&wait=true"
    use_fallback = False
    fallback_reason = ""

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, json=payload)
            if resp.status_code not in (200, 201):
                use_fallback = True
                fallback_reason = f"Judge0 returned status code {resp.status_code}"
            else:
                result = resp.json()
                status_id = result.get("status", {}).get("id")
                # Status 13 is Internal Error (often sandbox/cgroup allocation issues on WSL2)
                if status_id == 13:
                    use_fallback = True
                    fallback_reason = f"Judge0 sandbox internal error: {result.get('message')}"
                else:
                    return {
                        "status": "success",
                        "status_id": status_id,
                        "status_description": result.get("status", {}).get("description"),
                        "stdout": b64_decode(result.get("stdout") or ""),
                        "stderr": b64_decode(result.get("stderr") or ""),
                        "compile_output": b64_decode(result.get("compile_output") or ""),
                        "time": float(result.get("time") or 0.0),
                        "memory": int(result.get("memory") or 0)
                    }
    except Exception as e:
        use_fallback = True
        fallback_reason = str(e)

    if use_fallback:
        print(f"Judge0 execution bypassed (Reason: {fallback_reason}). Falling back to local Docker execution...")
        try:
            local_res = local_run_code(code, language)
            if local_res["status"] == "success":
                exit_code = local_res.get("exit_code", 0)
                stdout_content = local_res.get("stdout", "")
                stderr_content = local_res.get("stderr", "")
                output_str = local_res.get("output", "")

                if exit_code == 0:
                    return {
                        "status": "success",
                        "status_id": 3,  # Accepted
                        "status_description": "Accepted",
                        "stdout": stdout_content,
                        "stderr": stderr_content,
                        "compile_output": "",
                        "time": 0.0,
                        "memory": 0
                    }
                else:
                    is_compile_err = (
                        "compile" in output_str.lower() or 
                        "javac" in output_str.lower() or 
                        "g++" in output_str.lower() or 
                        "syntaxerror" in output_str.lower() or 
                        "indentationerror" in output_str.lower()
                    )
                    return {
                        "status": "success",
                        "status_id": 6 if is_compile_err else 11,  # Compilation Error vs Runtime Error
                        "status_description": "Compilation Error" if is_compile_err else "Runtime Error",
                        "stdout": stdout_content,
                        "stderr": stderr_content,
                        "compile_output": output_str if is_compile_err else "",
                        "time": 0.0,
                        "memory": 0
                    }
            else:
                output_str = local_res.get("output", "")
                is_timeout = "time limit exceeded" in output_str.lower()
                return {
                    "status": "success",
                    "status_id": 5 if is_timeout else 11,  # Time Limit Exceeded vs Runtime Error
                    "status_description": "Time Limit Exceeded" if is_timeout else "Runtime Error",
                    "stdout": "",
                    "stderr": output_str,
                    "compile_output": "",
                    "time": 0.0,
                    "memory": 0
                }
        except Exception as e:
            return {
                "status": "error",
                "error_detail": f"Fallback execution failed: {str(e)}"
            }

def evaluate_solution(
    user_code: str,
    language: str,
    problem_meta_data: Dict[str, Any],
    testcases_str: str,
    reference_python_code: str
) -> List[Dict[str, Any]]:
    """
    Evaluates user code by:
    1. Running the reference solution in Python to compute expected outputs.
    2. Running the user's code in the chosen language.
    3. Formatting test case comparisons.
    """
    from services.code_runner.template_generator import generate_wrapper

    # Parse parameters count
    params = problem_meta_data.get("params", [])
    num_params = len(params) if params else 1
    
    # Split testcase string into input chunks
    raw_lines = [line.strip() for line in testcases_str.strip().splitlines()]
    non_empty_lines = [line for line in raw_lines if line]
    
    testcase_inputs = []
    for chunk_idx in range(0, len(non_empty_lines), num_params):
        chunk = non_empty_lines[chunk_idx:chunk_idx+num_params]
        if len(chunk) < num_params:
            break
        testcase_inputs.append("\n".join(chunk))
        
    num_testcases = len(testcase_inputs)

    # 1. Run reference python solution to get expected outputs
    wrapped_ref_code = generate_wrapper(
        user_code=reference_python_code,
        language="python",
        meta_data=problem_meta_data,
        testcase_str=testcases_str
    )
    
    ref_run = submit_to_judge0(wrapped_ref_code, "python")
    if ref_run["status"] == "error" or ref_run.get("status_id") != 3:
        error_msg = ref_run.get("compile_output") or ref_run.get("stderr") or ref_run.get("error_detail") or "Unknown error"
        raise ValueError(f"Failed to execute reference solution: {error_msg}")

    # Parse expected outputs from reference run stdout
    expected_outputs = []
    for line in ref_run["stdout"].splitlines():
        if line.startswith("Output:"):
            expected_outputs.append(line[len("Output:"):].strip())

    # Ensure expected outputs match test case count
    while len(expected_outputs) < num_testcases:
        expected_outputs.append("N/A (Reference solution did not print output for this case)")

    # 2. Run user solution
    wrapped_user_code = generate_wrapper(
        user_code=user_code,
        language=language,
        meta_data=problem_meta_data,
        testcase_str=testcases_str
    )

    user_run = submit_to_judge0(wrapped_user_code, language, expected_output=ref_run["stdout"])
    
    # Check for compilation or connection errors
    status_id = user_run.get("status_id")
    actual_outputs = []
    
    # Parse actual outputs if code executed
    if user_run["status"] == "success" and user_run.get("stdout"):
        for line in user_run["stdout"].splitlines():
            if line.startswith("Output:"):
                actual_outputs.append(line[len("Output:"):].strip())

    while len(actual_outputs) < num_testcases:
        actual_outputs.append("N/A")

    # Construct granular results for each test case
    testcase_results = []
    for idx in range(num_testcases):
        inp = testcase_inputs[idx]
        expected = expected_outputs[idx]
        actual = actual_outputs[idx]
        
        # Determine pass/fail status
        passed = False
        error_detail = None
        
        if user_run["status"] == "error":
            error_detail = user_run.get("error_detail")
        elif status_id == 6: # Compilation Error
            error_detail = user_run.get("compile_output")
        elif status_id in (5, 7, 8, 9, 10, 11, 12): # Runtime error or timeout
            error_detail = user_run.get("stderr") or user_run.get("status_description") or "Runtime Error"
        else:
            # Standard string equality (cleaning trailing whitespace/JSON spacing differences)
            try:
                # Attempt structural comparison if both are valid JSON
                passed = json.loads(actual) == json.loads(expected)
            except Exception:
                passed = actual.strip() == expected.strip()
                
            if not passed:
                error_detail = "Wrong Answer"

        testcase_results.append({
            "passed": passed,
            "input": inp,
            "expected": expected,
            "actual": actual if actual != "N/A" else None,
            "error": error_detail,
            "is_edge_case": idx >= 2 # Treat subsequent test cases as edge cases
        })

    return testcase_results
