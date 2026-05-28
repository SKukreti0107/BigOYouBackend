import uuid
import re
import json
import httpx
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Optional
from sqlmodel import Session, select, or_
from helpers.auth.auth_deps import get_current_user
from modules.db import engine, Problems, Problem_topics, Interview_Session, Session_Feedback, Problem_Reference
from helpers.redis.redis_client import redis_conn
from services.ai_agent.langgraph_agent.llm import base_llm

class LeetCodeImportRequest(BaseModel):
    url: str

class GeneratedProblemDetails(BaseModel):
    example: str = Field(description="A clean, structured string showing one or two examples with Input and Output, formatted nicely.")
    expected_time: int = Field(description="Estimated time in minutes for a candidate to solve this problem (typically 15-20 for Easy, 30-40 for Medium, 45-60 for Hard).")
    optimal_approach: str = Field(description="Detailed explanation of the optimal strategy/algorithm to solve the problem.")
    time_complexity: str = Field(description="Big-O time complexity of the optimal strategy, e.g. O(N), O(N log N).")
    space_complexity: str = Field(description="Big-O space complexity of the optimal strategy, e.g. O(1), O(N).")
    key_insights: str = Field(description="Key observations or mathematical properties needed to solve the problem efficiently.")
    common_pitfalls: str = Field(description="Common mistakes, edge cases, or suboptimal approaches candidates make.")
    pseudocode: str = Field(description="Clean, well-commented, complete, and syntactically correct Python solution code.")
    pseudocode_cpp: str = Field(description="Clean, well-commented, complete, and syntactically correct C++ solution code inside the Solution class.")
    pseudocode_java: str = Field(description="Clean, well-commented, complete, and syntactically correct Java solution code inside the Solution class.")

class HiddenTestcaseInput(BaseModel):
    inputs: List[str] = Field(description="A list of inputs. If the function takes K parameters, this list must contain K elements representing the values of the parameters in order (e.g. as strings or JSON strings).")

class HiddenTestcasesList(BaseModel):
    testcases: List[HiddenTestcaseInput] = Field(description="A list of 5-8 robust edge-case test cases.")

def generate_and_validate_hidden_testcases(
    title: str,
    statement: str,
    parsed_meta: dict,
    example_testcases: Optional[str],
    sample_testcase: Optional[str],
    pseudocode: str
) -> str:
    """
    Generates 5-8 robust edge-case test cases using base_llm.
    Validates them by executing against the Python reference solution.
    If execution fails or cgroup/runner issues occur, falls back to example_testcases or sample_testcase.
    """
    params = parsed_meta.get("params", [])
    num_params = len(params) if params else 1
    
    # Prompt the LLM to generate the test cases
    prompt_text = f"""
You are a QA engineer and algorithm tester.
We are seeding a coding problem:
Title: {title}
Statement: {statement}
Metadata: {json.dumps(parsed_meta)}
Example test cases: {example_testcases or sample_testcase or "None"}

Generate 5-8 robust edge-case test cases to validate solutions for this problem.
Include inputs that test boundaries, edge cases, empty inputs (if allowed), large values, and typical scenarios.
The problem requires exactly {num_params} parameters per test case.
For each test case, you must provide exactly {num_params} values corresponding to the parameters in order: {', '.join(params) if params else 'input'}.
"""
    
    try:
        generated = base_llm.with_structured_output(HiddenTestcasesList).invoke(prompt_text)
        
        # Format the testcases into a single string
        testcase_lines = []
        for tc in generated.testcases:
            # Validate parameter count per testcase
            if len(tc.inputs) == num_params:
                for param_val in tc.inputs:
                    testcase_lines.append(str(param_val).strip())
            else:
                print(f"Warning: Test case had {len(tc.inputs)} inputs, expected {num_params}. Skipping.")
                
        testcases_str = "\n".join(testcase_lines)
        
        # Now validate it by running against the Python reference solution
        if testcases_str:
            from services.code_runner.judge import submit_to_judge0
            from services.code_runner.template_generator import generate_wrapper
            
            wrapped_ref_code = generate_wrapper(
                user_code=pseudocode,
                language="python",
                meta_data=parsed_meta,
                testcase_str=testcases_str
            )
            
            ref_run = submit_to_judge0(wrapped_ref_code, "python")
            
            if ref_run.get("status") == "success" and ref_run.get("status_id") == 3:
                print(f"Successfully validated {len(generated.testcases)} generated hidden test cases for '{title}'.")
                return testcases_str
            else:
                print(f"Validation failed for generated test cases. Status ID: {ref_run.get('status_id')}, Error: {ref_run.get('stderr') or ref_run.get('compile_output')}")
    except Exception as e:
        print(f"Error generating/validating hidden test cases for '{title}': {e}")
        
    print(f"Falling back to example/sample test cases for '{title}'.")
    fallback = example_testcases or sample_testcase or ""
    return fallback

def clean_html(html_content: str) -> str:
    if not html_content:
        return ""
    text = html_content
    text = re.sub(r'</?(p|div|pre|ul|ol|li)[^>]*>', '\n', text)
    text = re.sub(r'</?(code)[^>]*>', '`', text)
    text = re.sub(r'<br\s*/?>', '\n', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\n\s*\n', '\n\n', text)
    return text.strip()

def parse_leetcode_slug(url_or_slug: str) -> str:
    url_or_slug = url_or_slug.strip()
    match = re.search(r"leetcode\.com/problems/([^/\s?#]+)", url_or_slug)
    if match:
        return match.group(1)
    return url_or_slug

async def fetch_leetcode_question(title_slug: str) -> dict:
    url = "https://leetcode.com/graphql"
    headers = {
        "content-type": "application/json",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "referer": "https://leetcode.com/problems/",
    }
    
    query = """
    query questionData($titleSlug: String!) {
      question(titleSlug: $titleSlug) {
        questionId
        questionFrontendId
        title
        titleSlug
        content
        difficulty
        topicTags {
          name
          slug
        }
        codeSnippets {
          lang
          langSlug
          code
        }
        exampleTestcases
        sampleTestCase
        metaData
        hints
        stats
        isPaidOnly
      }
    }
    """
    
    payload = {
        "query": query,
        "variables": {
            "titleSlug": title_slug
        }
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers, timeout=15.0)
        
    if response.status_code != 200:
        raise ValueError(f"LeetCode API error: HTTP {response.status_code}")
        
    data = response.json()
    if "errors" in data:
        raise ValueError(f"LeetCode API error: {data['errors'][0].get('message')}")
        
    q_data = data.get("data", {}).get("question")
    if not q_data:
        raise ValueError(f"Problem not found on LeetCode: '{title_slug}'")
        
    if q_data.get("isPaidOnly"):
        raise ValueError(f"Problem '{title_slug}' is paid-only on LeetCode.")
        
    return q_data

router = APIRouter()

@router.get("/problems")
def get_problems(user_id: str = Depends(get_current_user)):
    try:
        user_id = uuid.UUID(user_id)
        with Session(engine) as session:
            statement = (
                select(
                    Problem_topics.topic,
                    Problems.problem_id,
                    Problems.title,
                    Problems.user_id,
                    Interview_Session.status,
                    Session_Feedback.final_score
                )
                .select_from(Problem_topics)
                .join(Problems, Problem_topics.problem_id == Problems.problem_id)
                .where(or_(Problems.user_id == None, Problems.user_id == user_id))
                .outerjoin(
                    Interview_Session,
                    (Interview_Session.problem_id == Problems.problem_id)
                    & (Interview_Session.user_id == user_id)
                )
                .outerjoin(
                    Session_Feedback,
                    Session_Feedback.session_id == Interview_Session.session_id
                )
            )

            rows = session.exec(statement).all()
            
            # Group by topic, then by problem_id to handle multiple sessions per problem
            topics_map = {}
            for row in rows:
                topic = row[0]
                prob_id = row[1]
                title = row[2]
                db_user_id = row[3]
                status = row[4]
                score = row[5]
                
                if topic not in topics_map:
                    topics_map[topic] = {}
                
                prob_id_str = str(prob_id)
                if prob_id_str not in topics_map[topic]:
                    topics_map[topic][prob_id_str] = {
                        "problem_id": prob_id_str,
                        "title": title,
                        "is_imported": db_user_id is not None,
                        "sessions": []
                    }
                
                if status is not None:
                    topics_map[topic][prob_id_str]["sessions"].append({
                        "status": status,
                        "score": score
                    })

            payload = []
            for topic, p_dict in topics_map.items():
                problems_list = []
                completed_count = 0
                total_count = len(p_dict)
                
                for p_id, p_info in p_dict.items():
                    sessions_list = p_info["sessions"]
                    is_completed = False
                    is_reattempt = False
                    highest_score = None
                    
                    for s in sessions_list:
                        score = s["score"]
                        status = s["status"]
                        
                        if score is not None:
                            if highest_score is None or score > highest_score:
                                highest_score = score
                                
                        # Question is completed only if session status is CLOSED and score is strictly > 70
                        if status == "CLOSED" and score is not None:
                            if score > 70:
                                is_completed = True
                                
                    # If not completed, it is a Suggested Reattempt if at least one session is CLOSED and score <= 70
                    if not is_completed:
                        for s in sessions_list:
                            status = s["status"]
                            score = s["score"]
                            if status == "CLOSED" and score is not None and score <= 70:
                                is_reattempt = True
                                break
                                
                    if is_completed:
                        completed_count += 1
                        
                    problems_list.append({
                        "id": p_id, # Frontend uses p.id, so we return it as "id"
                        "title": p_info["title"],
                        "is_completed": is_completed,
                        "is_reattempt": is_reattempt,
                        "score": highest_score,
                        "is_imported": p_info["is_imported"]
                    })
                
                # Sort problems by title for consistency
                problems_list = sorted(problems_list, key=lambda x: x["title"])
                
                payload.append({
                    "topic": topic,
                    "total": total_count,
                    "completed": completed_count,
                    "problems": problems_list
                })
                
            # Sort topics alphabetically
            payload = sorted(payload, key=lambda x: x["topic"])
            return payload

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user_id")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"error fetching problems: {e}")

@router.post("/problems/import-leetcode")
async def import_leetcode_problems(
    payload: LeetCodeImportRequest,
    user_id: str = Depends(get_current_user)
):
    try:
        # Rate limit check: max 5 imports per user per 15 minutes
        rate_limit_key = f"rate_limit:leetcode_import:{user_id}"
        current_count = redis_conn.get(rate_limit_key)
        if current_count and int(current_count) >= 5:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. You can only import up to 5 LeetCode problems every 15 minutes."
            )
            
        urls_or_slugs = [u.strip() for u in payload.url.split(",") if u.strip()]
        if not urls_or_slugs:
            raise HTTPException(status_code=400, detail="No URLs or slugs provided.")
            
        # Increment rate limiter
        val = redis_conn.incr(rate_limit_key)
        if val == 1:
            redis_conn.expire(rate_limit_key, 900)
            
        imported_count = 0
        already_imported = []
        errors = []
        
        for item in urls_or_slugs:
            title_slug = parse_leetcode_slug(item)
            if not title_slug:
                errors.append(f"Could not parse slug from input: '{item}'")
                continue
                
            try:
                # 1. Check if problem already exists in DB
                with Session(engine) as session:
                    existing = session.exec(
                        select(Problems).where(
                            (Problems.leetcode_slug == title_slug) &
                            ((Problems.user_id == None) | (Problems.user_id == uuid.UUID(user_id)))
                        )
                    ).first()
                    if not existing:
                        # Case insensitive/exact check on title format
                        expected_title = title_slug.replace("-", " ").title()
                        existing = session.exec(
                            select(Problems).where(
                                (Problems.title == expected_title) &
                                ((Problems.user_id == None) | (Problems.user_id == uuid.UUID(user_id)))
                            )
                        ).first()
                        
                    if existing:
                        already_imported.append(existing.title)
                        continue
                        
                # 2. Redis Cache Lookup for LeetCode API response
                cache_key = f"leetcode_cache:{title_slug}"
                cached_data = redis_conn.get(cache_key)
                
                if cached_data:
                    leetcode_data = json.loads(cached_data)
                else:
                    leetcode_data = await fetch_leetcode_question(title_slug)
                    # Cache response for 24 hours (86400 seconds)
                    redis_conn.setex(cache_key, 86400, json.dumps(leetcode_data))
                    
                # 3. Clean description statement HTML
                cleaned_statement = clean_html(leetcode_data.get("content", ""))
                
                # 4. Extract starter code snippets
                code_templates = ""
                for s in leetcode_data.get("codeSnippets", []):
                    code_templates += f"Language: {s.get('lang')}\nCode:\n{s.get('code')}\n\n"
                    
                # 5. Invoke Gemini LLM to compile optimal reference data
                prompt_text = f"""
You are a senior FAANG interviewer and algorithm expert.
We are importing a coding problem from LeetCode. Below is the raw problem metadata:

Title: {leetcode_data["title"]}
Difficulty: {leetcode_data["difficulty"]}
Topics: {", ".join([t.get("name", "") for t in leetcode_data.get("topicTags", [])])}
Statement / Description:
{cleaned_statement}

Starter Code Templates:
{code_templates}

Generate the detailed evaluation reference data for this coding problem:
1. `example`: Extrapolate one or two clear examples showing Input, Output, and an Explanation. Format it clearly.
2. `expected_time`: Provide a reasonable expected completion time in minutes (Easy: 15-20, Medium: 30-40, Hard: 45-60).
3. `optimal_approach`: Provide a clear description of the optimal strategy/algorithm.
4. `time_complexity` & `space_complexity`: Provide Big-O complexities.
5. `key_insights`: List key insights or observations needed to solve the problem.
6. `common_pitfalls`: List common bugs, edge cases, and pitfalls.
7. `pseudocode`: Write a complete, production-ready, fully commented Python solution matching the optimal approach.
8. `pseudocode_cpp`: Write a complete, production-ready, fully commented C++ solution matching the optimal approach, matching the class/method structure from the C++ starter template if provided.
9. `pseudocode_java`: Write a complete, production-ready, fully commented Java solution matching the optimal approach, matching the class/method structure from the Java starter template if provided.
"""
                generated = base_llm.with_structured_output(GeneratedProblemDetails).invoke(prompt_text)
                
                # Parse metaData string into a normalized dict
                meta_str = leetcode_data.get("metaData")
                parsed_meta = {}
                if meta_str:
                    try:
                        meta_json = json.loads(meta_str)
                        parsed_meta = {
                            "raw": meta_json,
                            "entry_method": meta_json.get("name"),
                            "params": [p.get("type") for p in meta_json.get("params", [])] if meta_json.get("params") else [],
                            "return_type": meta_json.get("return", {}).get("type") if meta_json.get("return") else None
                        }
                    except Exception:
                        pass

                # Generate and validate hidden test cases
                hidden_testcases_str = generate_and_validate_hidden_testcases(
                    title=leetcode_data["title"],
                    statement=cleaned_statement,
                    parsed_meta=parsed_meta,
                    example_testcases=leetcode_data.get("exampleTestcases"),
                    sample_testcase=leetcode_data.get("sampleTestCase"),
                    pseudocode=generated.pseudocode
                )

                # 6. Save problem, reference, and topics within a single session transaction
                with Session(engine) as session:
                    problem = Problems(
                        title=leetcode_data["title"],
                        statement=cleaned_statement,
                        example=generated.example,
                        difficulty=leetcode_data["difficulty"],
                        expected_time=generated.expected_time,
                        leetcode_slug=title_slug,
                        leetcode_url=f"https://leetcode.com/problems/{title_slug}/",
                        user_id=uuid.UUID(user_id),
                        code_snippets=leetcode_data.get("codeSnippets"),
                        meta_data=parsed_meta,
                        example_testcases=leetcode_data.get("exampleTestcases"),
                        sample_testcase=leetcode_data.get("sampleTestCase"),
                        hidden_testcases=hidden_testcases_str
                    )
                    session.add(problem)
                    session.commit()
                    session.refresh(problem)
                    
                    ref = Problem_Reference(
                        problem_id=problem.problem_id,
                        optimal_approach=generated.optimal_approach,
                        time_complexity=generated.time_complexity,
                        space_complexity=generated.space_complexity,
                        key_insights=generated.key_insights,
                        common_pitfalls=generated.common_pitfalls,
                        pseudocode=generated.pseudocode,
                        pseudocode_cpp=generated.pseudocode_cpp,
                        pseudocode_java=generated.pseudocode_java
                    )
                    session.add(ref)
                    
                    # Add topics
                    topics = leetcode_data.get("topicTags", [])
                    for t in topics:
                        topic_name = t.get("name")
                        if topic_name:
                            session.add(Problem_topics(problem_id=problem.problem_id, topic=topic_name))
                    if not topics:
                        session.add(Problem_topics(problem_id=problem.problem_id, topic="LeetCode Import"))
                        
                    session.commit()
                    imported_count += 1
                    
            except Exception as e:
                errors.append(f"Failed to import '{title_slug}': {str(e)}")
                
        return {
            "success": True,
            "imported_count": imported_count,
            "already_imported": already_imported,
            "errors": errors
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
