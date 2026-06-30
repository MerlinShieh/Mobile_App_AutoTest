"""临时语法验证脚本"""
import ast
import os

base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src", "mobile_automation")
files = [
    os.path.join(base, "llm", "__init__.py"),
    os.path.join(base, "llm", "base.py"),
    os.path.join(base, "llm", "qwen_adapter.py"),
    os.path.join(base, "llm", "openai_adapter.py"),
    os.path.join(base, "llm", "claude_adapter.py"),
    os.path.join(base, "llm", "llm_service.py"),
    os.path.join(base, "llm", "message_builder.py"),
    os.path.join(base, "llm", "token_budget.py"),
    os.path.join(base, "prompts", "__init__.py"),
    os.path.join(base, "prompts", "system_prompt.py"),
    os.path.join(base, "prompts", "decision_prompt.py"),
    os.path.join(base, "prompts", "summary_prompt.py"),
]

all_ok = True
for f in files:
    try:
        with open(f, encoding="utf-8") as fh:
            ast.parse(fh.read())
        print(f"OK: {os.path.basename(f)}")
    except SyntaxError as e:
        print(f"ERROR: {os.path.basename(f)}: {e}")
        all_ok = False

if all_ok:
    print("\n所有文件语法正确！")
else:
    print("\n存在语法错误！")
    exit(1)
