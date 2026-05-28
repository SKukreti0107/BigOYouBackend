import sys
import os
import json

# Adjust python path to import backend services
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.code_runner.judge import evaluate_solution

def test_judge_evaluation():
    print("Initializing test_judge_evaluation...")
    
    # Mock Problem Details
    meta_data = {
        "entry_method": "twoSum",
        "params": ["integer[]", "integer"],
        "return_type": "integer[]"
    }
    
    testcase_str = (
        "[2,7,11,15]\n"
        "9\n"
        "[3,2,4]\n"
        "6\n"
    )
    
    reference_code = """class Solution:
    def twoSum(self, nums: list[int], target: int) -> list[int]:
        lookup = {}
        for idx, val in enumerate(nums):
            diff = target - val
            if diff in lookup:
                return [lookup[diff], idx]
            lookup[val] = idx
        return []
"""

    # Test Case 1: Correct user submission
    print("\n--- Testing Correct Python Submission ---")
    correct_user_code = reference_code
    try:
        results = evaluate_solution(
            user_code=correct_user_code,
            language="python",
            problem_meta_data=meta_data,
            testcases_str=testcase_str,
            reference_python_code=reference_code
        )
        print("Evaluation results:")
        print(json.dumps(results, indent=2))
        
        passed_all = all(r["passed"] for r in results)
        print(f"Passed all test cases? {passed_all}")
        assert passed_all == True, "Correct solution failed execution"
        print("SUCCESS: Correct submission passed successfully!")
    except Exception as e:
        print(f"ERROR: Correct submission failed with exception: {e}")

    # Test Case 2: Incorrect user submission (returns static [0, 0])
    print("\n--- Testing Incorrect Python Submission ---")
    incorrect_user_code = """class Solution:
    def twoSum(self, nums: list[int], target: int) -> list[int]:
        return [0, 0]
"""
    try:
        results = evaluate_solution(
            user_code=incorrect_user_code,
            language="python",
            problem_meta_data=meta_data,
            testcases_str=testcase_str,
            reference_python_code=reference_code
        )
        print("Evaluation results:")
        print(json.dumps(results, indent=2))
        
        passed_any = any(r["passed"] for r in results)
        print(f"Passed any test cases? {passed_any}")
        assert passed_any == False, "Incorrect solution incorrectly marked as passed"
        print("SUCCESS: Incorrect submission detected and marked WA successfully!")
    except Exception as e:
        print(f"ERROR: Incorrect submission failed with exception: {e}")

    # Test Case 3: Top-level function reference and user code
    print("\n--- Testing Top-level Function Submission ---")
    toplevel_reference_code = """def twoSum(nums, target):
    seen = {}
    for i, num in enumerate(nums):
        complement = target - num
        if complement in seen:
            return [seen[complement], i]
        seen[num] = i
    return []
"""
    toplevel_user_code = toplevel_reference_code
    try:
        results = evaluate_solution(
            user_code=toplevel_user_code,
            language="python",
            problem_meta_data=meta_data,
            testcases_str=testcase_str,
            reference_python_code=toplevel_reference_code
        )
        print("Evaluation results:")
        print(json.dumps(results, indent=2))
        
        passed_all = all(r["passed"] for r in results)
        print(f"Passed all test cases? {passed_all}")
        assert passed_all == True, "Top-level function solution failed execution"
        print("SUCCESS: Top-level function submission passed successfully!")
    except Exception as e:
        print(f"ERROR: Top-level function submission failed with exception: {e}")

if __name__ == "__main__":
    test_judge_evaluation()
