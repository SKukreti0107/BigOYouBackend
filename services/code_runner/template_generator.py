import json

def generate_python_wrapper(user_code: str, meta_data: dict, testcase_str: str) -> str:
    entry_method = meta_data.get("entry_method")
    params = meta_data.get("params", [])
    num_params = len(params)
    
    wrapper = f"""import math
import collections
import heapq
import bisect
import functools
import itertools
from typing import List, Dict, Tuple, Optional, Any, Set, Union, Deque

{user_code}

# --- Auto-generated Runner Code ---
import json
import sys

def parse_input(val, type_str):
    val = val.strip()
    if not val:
        return None
    if type_str.endswith("[]") or type_str.startswith("list<"):
        return json.loads(val)
    elif type_str == "integer":
        return int(val)
    elif type_str == "double":
        return float(val)
    elif type_str == "string":
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            return val[1:-1]
        return val
    elif type_str == "boolean":
        return val.lower() == "true"
    elif type_str == "character":
        if (val.startswith("'") and val.endswith("'")) or (val.startswith('"') and val.endswith('"')):
            return val[1:-1]
        return val
    return json.loads(val)

if __name__ == "__main__":
    testcases = {repr(testcase_str)}
    lines = [line.strip() for line in testcases.strip().splitlines() if line.strip()]
    num_params = {num_params}
    param_types = {repr(params)}
    
    for chunk_idx in range(0, len(lines), num_params):
        chunk = lines[chunk_idx:chunk_idx+num_params]
        if len(chunk) < num_params:
            break
        try:
            parsed_params = []
            for i, p_type in enumerate(param_types):
                parsed_params.append(parse_input(chunk[i], p_type))
            
            if 'Solution' in globals():
                sol = Solution()
                res = getattr(sol, '{entry_method}')(*parsed_params)
            elif '{entry_method}' in globals():
                res = globals()['{entry_method}'](*parsed_params)
            else:
                raise NameError("Neither 'Solution' class nor function '{entry_method}' found.")
            print("Output:", json.dumps(res))
        except Exception as e:
            print("Error executing solution:", e, file=sys.stderr)
            sys.exit(1)
"""
    return wrapper

def generate_cpp_wrapper(user_code: str, meta_data: dict, testcase_str: str) -> str:
    entry_method = meta_data.get("entry_method")
    params = meta_data.get("params", [])
    num_params = len(params)
    
    type_map = {
        "integer": "int",
        "integer[]": "std::vector<int>",
        "list<integer>": "std::vector<int>",
        "double": "double",
        "double[]": "std::vector<double>",
        "list<double>": "std::vector<double>",
        "string": "std::string",
        "string[]": "std::vector<std::string>",
        "list<string>": "std::vector<std::string>",
        "boolean": "bool",
        "character": "char",
        "character[]": "std::vector<char>",
        "list<character>": "std::vector<char>"
    }
    
    parser_calls = []
    for i, p_type in enumerate(params):
        if p_type == "integer[]" or p_type == "list<integer>":
            parser_calls.append(f"parse_int_array(lines[{i}])")
        elif p_type == "integer":
            parser_calls.append(f"parse_int(lines[{i}])")
        elif p_type == "double[]" or p_type == "list<double>":
            parser_calls.append(f"parse_double_array(lines[{i}])")
        elif p_type == "double":
            parser_calls.append(f"parse_double(lines[{i}])")
        elif p_type == "string[]" or p_type == "list<string>":
            parser_calls.append(f"parse_string_array(lines[{i}])")
        elif p_type == "string":
            parser_calls.append(f"parse_string(lines[{i}])")
        elif p_type == "boolean":
            parser_calls.append(f"parse_bool(lines[{i}])")
        elif p_type == "character[]" or p_type == "list<character>":
            parser_calls.append(f"parse_char_array(lines[{i}])")
        elif p_type == "character":
            parser_calls.append(f"parse_char(lines[{i}])")
        else:
            parser_calls.append(f"parse_string(lines[{i}])")
            
    call_args = ", ".join([f"param{i}" for i in range(num_params)])
    
    parse_blocks = []
    for i, p_type in enumerate(params):
        cpp_type = type_map.get(p_type, "std::string")
        parse_blocks.append(f"{cpp_type} p{i} = {parser_calls[i]};")
        
    sol_call_args = ", ".join([f"p{i}" for i in range(num_params)])

    wrapper = f"""#include <iostream>
#include <vector>
#include <string>
#include <sstream>
#include <algorithm>
#include <cctype>
#include <unordered_map>
#include <unordered_set>
#include <map>
#include <set>
#include <queue>
#include <stack>
#include <utility>
#include <cmath>
#include <climits>

using namespace std;

{user_code}

// --- Auto-generated Runner Code ---

int parse_int(const std::string& s) {{
    return std::stoi(s);
}}

double parse_double(const std::string& s) {{
    return std::stod(s);
}}

bool parse_bool(const std::string& s) {{
    std::string temp = s;
    std::transform(temp.begin(), temp.end(), temp.begin(), ::tolower);
    return temp == "true" || temp == "1";
}}

char parse_char(const std::string& s) {{
    std::string temp = s;
    if (temp.size() >= 3 && temp.front() == '\'' && temp.back() == '\'') {{
        return temp[1];
    }}
    return temp.empty() ? '\\0' : temp[0];
}}

std::string parse_string(const std::string& s) {{
    std::string temp = s;
    if (temp.size() >= 2 && temp.front() == '"' && temp.back() == '"') {{
        return temp.substr(1, temp.size() - 2);
    }}
    return temp;
}}

std::vector<int> parse_int_array(const std::string& s) {{
    std::vector<int> res;
    std::string clean = s;
    clean.erase(std::remove(clean.begin(), clean.end(), '['), clean.end());
    clean.erase(std::remove(clean.begin(), clean.end(), ']'), clean.end());
    std::stringstream ss(clean);
    std::string item;
    while (std::getline(ss, item, ',')) {{
        if (!item.empty()) res.push_back(std::stoi(item));
    }}
    return res;
}}

std::vector<double> parse_double_array(const std::string& s) {{
    std::vector<double> res;
    std::string clean = s;
    clean.erase(std::remove(clean.begin(), clean.end(), '['), clean.end());
    clean.erase(std::remove(clean.begin(), clean.end(), ']'), clean.end());
    std::stringstream ss(clean);
    std::string item;
    while (std::getline(ss, item, ',')) {{
        if (!item.empty()) res.push_back(std::stod(item));
    }}
    return res;
}}

std::vector<char> parse_char_array(const std::string& s) {{
    std::vector<char> res;
    std::string clean = s;
    clean.erase(std::remove(clean.begin(), clean.end(), '['), clean.end());
    clean.erase(std::remove(clean.begin(), clean.end(), ']'), clean.end());
    std::stringstream ss(clean);
    std::string item;
    while (std::getline(ss, item, ',')) {{
        while(!item.empty() && std::isspace(item.front())) item.erase(0, 1);
        while(!item.empty() && std::isspace(item.back())) item.pop_back();
        if (item.size() >= 3 && item.front() == '\'' && item.back() == '\'') {{
            res.push_back(item[1]);
        }} else if (!item.empty()) {{
            res.push_back(item[0]);
        }}
    }}
    return res;
}}

std::vector<std::string> parse_string_array(const std::string& s) {{
    std::vector<std::string> res;
    std::string clean = s;
    if (clean.size() >= 2 && clean.front() == '[' && clean.back() == ']') {{
        clean = clean.substr(1, clean.size() - 2);
    }}
    std::stringstream ss(clean);
    std::string item;
    while (std::getline(ss, item, ',')) {{
        while(!item.empty() && std::isspace(item.front())) item.erase(0, 1);
        while(!item.empty() && std::isspace(item.back())) item.pop_back();
        if (item.size() >= 2 && item.front() == '"' && item.back() == '"') {{
            item = item.substr(1, item.size() - 2);
        }}
        res.push_back(item);
    }}
    return res;
}}

void print_val(int v) {{ std::cout << v; }}
void print_val(double v) {{ std::cout << v; }}
void print_val(bool v) {{ std::cout << (v ? "true" : "false"); }}
void print_val(char v) {{ std::cout << "'" << v << "'"; }}
void print_val(const std::string& v) {{ std::cout << "\\"" << v << "\\""; }}

template<typename T>
void print_array(const std::vector<T>& v) {{
    std::cout << "[";
    for (size_t i = 0; i < v.size(); ++i) {{
        print_val(v[i]);
        if (i + 1 < v.size()) std::cout << ",";
    }}
    std::cout << "]";
}}

void print_val(const std::vector<int>& v) {{ print_array(v); }}
void print_val(const std::vector<double>& v) {{ print_array(v); }}
void print_val(const std::vector<std::string>& v) {{ print_array(v); }}
void print_val(const std::vector<char>& v) {{ print_array(v); }}

int main() {{
    std::string testcase_data = {repr(testcase_str)};
    std::stringstream ss(testcase_data);
    std::string line;
    std::vector<std::string> all_lines;
    while (std::getline(ss, line)) {{
        while(!line.empty() && std::isspace(line.back())) line.pop_back();
        while(!line.empty() && std::isspace(line.front())) line.erase(0, 1);
        if (!line.empty()) {{
            all_lines.push_back(line);
        }}
    }}
    
    int num_params = {num_params};
    for (size_t chunk_idx = 0; chunk_idx < all_lines.size(); chunk_idx += num_params) {{
        if (chunk_idx + num_params > all_lines.size()) break;
        std::vector<std::string> lines(all_lines.begin() + chunk_idx, all_lines.begin() + chunk_idx + num_params);
        try {{
            Solution sol;
            {" ".join(parse_blocks)}
            auto result = sol.{entry_method}({sol_call_args});
            std::cout << "Output: ";
            print_val(result);
            std::cout << std::endl;
        }} catch (const std::exception& e) {{
            std::cerr << "Exception: " << e.what() << std::endl;
            return 1;
        }}
    }}
    return 0;
}}
"""
    return wrapper

def generate_java_wrapper(user_code: str, meta_data: dict, testcase_str: str) -> str:
    entry_method = meta_data.get("entry_method")
    params = meta_data.get("params", [])
    num_params = len(params)
    
    type_map = {
        "integer": "int",
        "integer[]": "int[]",
        "list<integer>": "List<Integer>",
        "double": "double",
        "double[]": "double[]",
        "list<double>": "List<Double>",
        "string": "String",
        "string[]": "String[]",
        "list<string>": "List<String>",
        "boolean": "boolean",
        "character": "char",
        "character[]": "char[]",
        "list<character>": "List<Character>"
    }
    
    parser_calls = []
    for i, p_type in enumerate(params):
        if p_type == "integer[]":
            parser_calls.append(f"parse_int_array(lines.get({i}))")
        elif p_type == "list<integer>":
            parser_calls.append(f"parse_int_list(lines.get({i}))")
        elif p_type == "integer":
            parser_calls.append(f"parse_int(lines.get({i}))")
        elif p_type == "double[]":
            parser_calls.append(f"parse_double_array(lines.get({i}))")
        elif p_type == "list<double>":
            parser_calls.append(f"parse_double_list(lines.get({i}))")
        elif p_type == "double":
            parser_calls.append(f"parse_double(lines.get({i}))")
        elif p_type == "string[]":
            parser_calls.append(f"parse_string_array(lines.get({i}))")
        elif p_type == "list<string>":
            parser_calls.append(f"parse_string_list(lines.get({i}))")
        elif p_type == "string":
            parser_calls.append(f"parse_string(lines.get({i}))")
        elif p_type == "boolean":
            parser_calls.append(f"parse_bool(lines.get({i}))")
        elif p_type == "character[]":
            parser_calls.append(f"parse_char_array(lines.get({i}))")
        elif p_type == "list<character>":
            parser_calls.append(f"parse_char_list(lines.get({i}))")
        elif p_type == "character":
            parser_calls.append(f"parse_char(lines.get({i}))")
        else:
            parser_calls.append(f"parse_string(lines.get({i}))")

    parse_blocks = []
    for i, p_type in enumerate(params):
        java_type = type_map.get(p_type, "String")
        parse_blocks.append(f"{java_type} p{i} = {parser_calls[i]};")
        
    sol_call_args = ", ".join([f"p{i}" for i in range(num_params)])

    injected_code = f"""
    // --- Auto-generated Runner Code ---
    public static int parse_int(String s) {{
        return Integer.parseInt(s.trim());
    }}

    public static double parse_double(String s) {{
        return Double.parseDouble(s.trim());
    }}

    public static boolean parse_bool(String s) {{
        return Boolean.parseBoolean(s.trim().toLowerCase());
    }}

    public static char parse_char(String s) {{
        String t = s.trim();
        if (t.length() >= 3 && t.startsWith("'") && t.endsWith("'")) {{
            return t.charAt(1);
        }}
        return t.isEmpty() ? '\\0' : t.charAt(0);
    }}

    public static String parse_string(String s) {{
        String t = s.trim();
        if (t.length() >= 2 && t.startsWith("\\"") && t.endsWith("\\"")) {{
            return t.substring(1, t.length() - 1);
        }}
        return t;
    }}

    public static int[] parse_int_array(String s) {{
        String clean = s.trim().replace("[", "").replace("]", "");
        if (clean.isEmpty()) return new int[0];
        String[] parts = clean.split(",");
        int[] res = new int[parts.length];
        for (int i = 0; i < parts.length; i++) {{
            res[i] = Integer.parseInt(parts[i].trim());
        }}
        return res;
    }}

    public static List<Integer> parse_int_list(String s) {{
        int[] arr = parse_int_array(s);
        List<Integer> res = new ArrayList<>();
        for (int x : arr) res.add(x);
        return res;
    }}

    public static double[] parse_double_array(String s) {{
        String clean = s.trim().replace("[", "").replace("]", "");
        if (clean.isEmpty()) return new double[0];
        String[] parts = clean.split(",");
        double[] res = new double[parts.length];
        for (int i = 0; i < parts.length; i++) {{
            res[i] = Double.parseDouble(parts[i].trim());
        }}
        return res;
    }}

    public static List<Double> parse_double_list(String s) {{
        double[] arr = parse_double_array(s);
        List<Double> res = new ArrayList<>();
        for (double x : arr) res.add(x);
        return res;
    }}

    public static char[] parse_char_array(String s) {{
        String clean = s.trim().replace("[", "").replace("]", "");
        if (clean.isEmpty()) return new char[0];
        String[] parts = clean.split(",");
        char[] res = new char[parts.length];
        for (int i = 0; i < parts.length; i++) {{
            String p = parts[i].trim();
            if (p.startsWith("'") && p.endsWith("'") && p.length() >= 3) {{
                res[i] = p.charAt(1);
            }} else {{
                res[i] = p.isEmpty() ? '\\0' : p.charAt(0);
            }}
        }}
        return res;
    }}

    public static List<Character> parse_char_list(String s) {{
        char[] arr = parse_char_array(s);
        List<Character> res = new ArrayList<>();
        for (char x : arr) res.add(x);
        return res;
    }}

    public static String[] parse_string_array(String s) {{
        String clean = s.trim();
        if (clean.startsWith("[")) clean = clean.substring(1);
        if (clean.endsWith("]")) clean = clean.substring(0, clean.length() - 1);
        if (clean.isEmpty()) return new String[0];
        String[] parts = clean.split(",");
        String[] res = new String[parts.length];
        for (int i = 0; i < parts.length; i++) {{
            String p = parts[i].trim();
            if (p.startsWith("\\"") && p.endsWith("\\"") && p.length() >= 2) {{
                p = p.substring(1, p.length() - 1);
            }}
            res[i] = p;
        }}
        return res;
    }}

    public static List<String> parse_string_list(String s) {{
        return Arrays.asList(parse_string_array(s));
    }}

    public static void print_val(Object o) {{
        if (o instanceof int[]) {{
            System.out.print(Arrays.toString((int[]) o));
        }} else if (o instanceof double[]) {{
            System.out.print(Arrays.toString((double[]) o));
        }} else if (o instanceof char[]) {{
            System.out.print(Arrays.toString((char[]) o));
        }} else if (o instanceof Object[]) {{
            System.out.print(Arrays.toString((Object[]) o));
        }} else if (o instanceof String) {{
            System.out.print("\\"" + o + "\\"");
        }} else if (o instanceof Character) {{
            System.out.print("'" + o + "'");
        }} else if (o instanceof List) {{
            System.out.print(o);
        }} else {{
            System.out.print(o);
        }}
    }}

    public static void main(String[] args) {{
        String testcaseData = {repr(testcase_str)};
        String[] linesArray = testcaseData.split("\\r?\\n");
        List<String> allLines = new ArrayList<>();
        for (String line : linesArray) {{
            String t = line.trim();
            if (!t.isEmpty()) {{
                allLines.add(t);
            }}
        }}

        int numParams = {num_params};
        for (int chunkIdx = 0; chunkIdx < allLines.size(); chunkIdx += numParams) {{
            if (chunkIdx + numParams > allLines.size()) break;
            List<String> lines = allLines.subList(chunkIdx, chunkIdx + numParams);
            try {{
                Solution sol = new Solution();
                {" ".join(parse_blocks)}
                Object result = sol.{entry_method}({sol_call_args});
                System.out.print("Output: ");
                print_val(result);
                System.out.println();
            }} catch (Exception e) {{
                System.err.println("Exception: " + e.getMessage());
                System.exit(1);
            }}
        }}
    }}
"""

    last_brace_idx = user_code.rfind("}")
    imports = """import java.util.*;
import java.io.*;
import java.math.*;

"""
    if last_brace_idx != -1:
        return imports + user_code[:last_brace_idx] + injected_code + user_code[last_brace_idx:]
    else:
        return imports + user_code + "\nclass SolutionRunner {\n" + injected_code + "\n}"

def generate_wrapper(user_code: str, language: str, meta_data: dict, testcase_str: str) -> str:
    if not meta_data or not meta_data.get("entry_method"):
        return user_code
        
    if language == "python" or language == "python3":
        return generate_python_wrapper(user_code, meta_data, testcase_str)
    elif language == "cpp":
        return generate_cpp_wrapper(user_code, meta_data, testcase_str)
    elif language == "java":
        return generate_java_wrapper(user_code, meta_data, testcase_str)
        
    return user_code
