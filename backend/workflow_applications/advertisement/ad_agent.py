# -----------------------------------------------------------------------------
# © 2026 Artalor
# Artalor Project — All rights reserved.
# Licensed for personal and educational use only.
# Commercial use or redistribution prohibited.
# See LICENSE.md for full terms.
# -----------------------------------------------------------------------------

"""
Plan-and-Execute Agent
======================
Architecture based on LangChain official Plan-and-Execute pattern:
1. **Planner**: generate a complete task plan first
2. **Executor**: execute the steps one by one via ReAct + tools
3. **Reflect / Re-plan**: re-plan when a step fails or needs improvement

This script loads all real agent tools from `domain_components` and adds the
custom `auto_storyboard_designer` helper.
"""

import os
import sys
from typing import List
import re

from langchain_openai import ChatOpenAI
from langchain_experimental.plan_and_execute import (
    load_agent_executor,
    PlanAndExecute,
)
from langchain_experimental.plan_and_execute.planners.base import LLMPlanner
from langchain_experimental.plan_and_execute.schema import Plan, Step, PlanOutputParser
from langchain.chains import LLMChain
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate
from langchain_core.messages import SystemMessage

# ---------------------------------------------------------------------------
# 1. Import real tools
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from modules.tools.langchain_agent_tools import get_all_tools
from domain_components.generation.auto_storyboard_tool import AutoStoryboardDesignerTool
from modules.tools.multi_storyboard_video_tool import MultiStoryboardVideoGeneratorTool
from modules.tools.utils import load_env, ProgressIndicator, filter_description
load_env()

TOOLS = get_all_tools()
TOOLS.append(AutoStoryboardDesignerTool())
TOOLS.append(MultiStoryboardVideoGeneratorTool())

# ---------------------------------------------------------------------------
# 2. Initialize the LLM
# ---------------------------------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise EnvironmentError("❌ Please set OPENAI_API_KEY inside the .venv environment")

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# ---------------------------------------------------------------------------
# 3. Build Planner and Executor
# ---------------------------------------------------------------------------
tool_desc = "\n".join([f"- {t.name}: {t.description.splitlines()[0]}" for t in TOOLS])
system_prompt = (
    "You are a planning assistant for an autonomous agent. "
    "Here are the available tools that will be used during execution:\n" + tool_desc + "\n" +
    "Recommended high-level workflow: "
    "1) product_analyzer  ➜  ad_script_writer\n"
    "2) ad_script_writer (JSON)  ➜  auto_storyboard_designer\n"
    "3) auto_storyboard_designer  ➜  ad_storyboard_designer\n"
    "   (ad_storyboard_designer now returns **storyboards list** in 'storyboards' field)\n"
    "4) Pass the full design JSON to multi_storyboard_video_generator. This tool will:\n"
    "   • iterate over each storyboard\n"
    "   • generate keyframe images with image_generator\n"
    "   • compose a video for that storyboard with video_generator\n"
    "   • return a JSON containing 'videos' list.\n"
    "5) Output the videos list to the user.\n"
    "IMPORTANT: After each tool call, ALWAYS pass the ENTIRE JSON output of that tool directly as the input of the next one. Do NOT manually rewrite, summarise, or remove fields.\n"
    "Do not request extra input from user, always chain outputs. "
    "Output your plan starting with 'Plan:' followed by numbered steps, and finish with <END_OF_PLAN>."
)

# system_prompt = (
#     "You are a planning assistant for an autonomous agent. "
#     "Here are the available tools that will be used during execution:\n" + tool_desc + "\n" +
#     "When devising the plan, keep in mind these TOOL DEPENDENCIES (use them in the correct order, but feel free to merge or split steps as you see fit):\n"
#     "• product_analyzer  ➜  ad_script_writer\n"
#     "• ad_script_writer (JSON)  ➜  auto_storyboard_designer\n"
#     "• storyboard JSON  ➜  ad_storyboard_designer\n"
#     "• storyboard frames  ➜  image_generator (one keyframe image per frame)\n"
#     "• keyframe images + storyboard  ➜  video_generator (compose the final video)\n"
#     "Always pass outputs from earlier tools directly into later tools without asking the user for extra input.\n"
#     "Please output the plan starting with the header 'Plan:' and then a numbered list of steps. "
#     "End the plan with <END_OF_PLAN>."
# )
print("⚙️  Building Planner (LLM generates the task plan)…")

# Robust plan output parser (tolerant to formatting issues)
class RobustPlanningOutputParser(PlanOutputParser):
    def parse(self, text: str) -> Plan:
        txt = text.strip()
        # Remove header/footer markers
        if "Plan:" in txt:
            txt = txt.split("Plan:", 1)[1]
        txt = txt.replace("<END_OF_PLAN>", "").strip()

        # Split by numbering (supports patterns like '1.' or '1)')
        parts = re.split(r"\n\s*\d+[\.)]\s*", txt)
        steps = [Step(value=p.strip()) for p in parts if p.strip()]
        # Ensure at least one step even if parsing fails
        if not steps:
            steps = [Step(value=txt)]
        return Plan(steps=steps)

# Build the custom planner
prompt_template = ChatPromptTemplate.from_messages(
    [SystemMessage(content=system_prompt), HumanMessagePromptTemplate.from_template("{input}")]
)
llm_chain = LLMChain(llm=llm, prompt=prompt_template)
planner = LLMPlanner(llm_chain=llm_chain, output_parser=RobustPlanningOutputParser(), stop=["<END_OF_PLAN>"])

print("⚙️  Building Executor (ReAct agent executes the plan)…")
executor = load_agent_executor(llm, TOOLS, verbose=True)

# Allow the AgentExecutor to automatically retry on JSON parsing errors
if hasattr(executor, 'chain') and hasattr(executor.chain, 'handle_parsing_errors'):
    executor.chain.handle_parsing_errors = True

# ----------------------- executor ---------------------------
from langchain_experimental.plan_and_execute.executors.base import StepResponse, BaseExecutor, ChainExecutor
import json


class CustomExecutor(BaseExecutor):
    """Wrap the internal ChainExecutor, forcing its `.step` result to be a plain string."""

    executor: ChainExecutor

    def step(self, inputs: dict, callbacks=None, **kwargs):  # type: ignore[override]
        # Call the underlying chain.run directly to avoid premature StepResponse creation
        raw = self.executor.chain.run(**inputs, callbacks=callbacks)
        resp = raw
        print('DEBUG type', type(resp))
        if not isinstance(resp, str):
            resp = json.dumps(resp, ensure_ascii=False)
        return StepResponse(response=resp)

    async def astep(self, inputs: dict, callbacks=None, **kwargs):  # type: ignore[override]
        raw = await self.executor.chain.arun(**inputs, callbacks=callbacks)
        resp = raw
        print('DEBUG type', type(resp))
        if not isinstance(resp, str):
            resp = json.dumps(resp, ensure_ascii=False)
        return StepResponse(response=resp)


# Create CustomExecutor
custom_executor = CustomExecutor(executor=executor)

agent = PlanAndExecute(
    planner=planner,
    executor=custom_executor,
    verbose=True,           # Print PLAN / EXECUTION / REFLECT / REPLAN sections
    max_iterations=3,       # Maximum number of re-plan attempts
)

# ---------------------------------------------------------------------------
# 4. Run example task
# ---------------------------------------------------------------------------
QUERY = "Generate a complete video advertisement for this new optical-zoom smartphone"

print("\n📝 Input task: " + QUERY)
print("=" * 80)

result = agent.invoke({"input": QUERY})
print("\n" + "=" * 80)
print("✅ Final output:\n" + result["output"])