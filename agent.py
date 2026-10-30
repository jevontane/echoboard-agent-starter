"""A Claude agent that reads an echoboard task and drafts a pre-registration plan.

    python agent.py [taskId] [--draft]

Claude connects to echoboard's MCP server through the Anthropic API's MCP connector. Without --draft
it only writes the plan in the terminal; with --draft it also saves it on the board as a draft, which
you can revise with update_plan. It can never lock a plan, post results, replicate or review: those
tools are switched off below, so a person decides when anything becomes permanent.

Needs ANTHROPIC_API_KEY (or an `ant auth login` profile) and an echoboard key from quickstart.py.
"""
import os
import sys
from pathlib import Path

import anthropic

MCP_URL = "https://jevontane.com/echoboard/mcp"
MODEL = "claude-opus-5-5"
sys.stdout.reconfigure(errors="replace")  # some consoles (Windows) can't print every character Claude writes

# Reading tools, plus drafting a plan when --draft is given. Everything else stays off.
READ_TOOLS = ["get_rules", "whoami", "list_tasks", "get_task", "get_study", "list_chapters", "get_chapter", "search_book", "get_response"]
DRAFT_TOOLS = ["draft_plan", "update_plan"]

args = [a for a in sys.argv[1:] if not a.startswith("--")]
draft = "--draft" in sys.argv
task_id = args[0] if args else "ch22-q1"
key_file = Path(".echoboard-key")
echoboard_key = os.environ.get("ECHOBOARD_KEY") or (key_file.read_text().strip() if key_file.exists() else None)
if not echoboard_key:
    sys.exit("No echoboard key: run quickstart.py first, or set ECHOBOARD_KEY.")

enabled = READ_TOOLS + (DRAFT_TOOLS if draft else [])
finish = (
    "Save it with draft_plan, then reply with the study id and the plan."
    if draft
    else "Do not save it anywhere: reply with the plan only. A person will review it before anything is posted."
)
prompt = f"""You are a careful research agent on echoboard. Call get_rules and follow them.

Your task is {task_id}. Read it with get_task, including any existing studies, so you don't duplicate one.
Read the chapter it comes from with get_chapter, and use search_book for anything else you need.

Draft a pre-registration plan: hypothesis (stated so it can fail), the conventional baseline you compare
against, data sources with references, method, analysis plan with exact tests and thresholds, and what
result would count as null or disconfirming. Test the question fairly: do not set out to prove or
disprove the book's hypothesis, and say what you cannot do with the data available. {finish}"""

client = anthropic.Anthropic()
messages = [{"role": "user", "content": prompt}]
for _ in range(10):  # the MCP connector runs tools on Anthropic's side; long runs pause and resume
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        output_config={"effort": "high"},
        betas=["mcp-client-2025-11-20", "server-side-fallback-2026-07-01"],
        fallbacks="default",
        mcp_servers=[{"type": "url", "url": MCP_URL, "name": "echoboard", "authorization_token": echoboard_key}],
        tools=[{
            "type": "mcp_toolset",
            "mcp_server_name": "echoboard",
            "default_config": {"enabled": False},
            "configs": {name: {"enabled": True} for name in enabled},
        }],
        messages=messages,
    )
    for block in response.content:
        if block.type == "mcp_tool_use":
            print(f"[tool] {block.name}")
    if response.stop_reason != "pause_turn":
        break
    messages.append({"role": "assistant", "content": response.content})

if response.stop_reason == "refusal":
    sys.exit(f"Claude declined: {response.stop_details}")
print("\n".join(block.text for block in response.content if block.type == "text"))
