"""ProactiveReActAgent ReAct 循环各阶段的用户提示词模板.

使用 ``str.format`` 填充占位符, 占位符清单见各模板 docstring.
"""

# 占位符: name, task, context_text, history_text
REACT_THOUGHT_PROMPT_TEMPLATE = """You are {name}. Generate your next thought about the task.

Task: {task}
Context: {context_text}
History: {history_text}

Generate a thought about what you should consider or do next. Be specific and relevant to the task.

Only return the thought text, no JSON format."""

# 占位符: name, task, thought, history_text
REACT_REASONING_PROMPT_TEMPLATE = """You are {name}. Generate reasoning for your thought.

Task: {task}
Your thought: {thought}
History: {history_text}

Generate a reasoning that explains why you chose this thought. Consider:
- What information do you have?
- What do you need to verify?
- What are the risks or uncertainties?

Only return the reasoning text, no JSON format."""

# 占位符: name, thought, reasoning, beliefs_text
REACT_EVIDENCE_PROMPT_TEMPLATE = """You are {name}. Generate evidence for your reasoning.

Your thought: {thought}
Your reasoning: {reasoning}
Current beliefs: {beliefs_text}

Generate evidence that supports your reasoning. Cite specific sources or data.

Evidence (as JSON with keys like "sources", "data", "references"):"""

# 占位符: name, task, thought, history_text
REACT_ACTION_PROMPT_TEMPLATE = """You are {name}. Decide your next action.

Task: {task}
Your thought: {thought}
History: {history_text}

Choose an action type and parameters:
- "llm_call": Make another LLM call to gather more information
- "tool_call": Execute a tool (specify tool_name and params)
- "finalize": Task is complete, generate final answer

Return as JSON with "action_type" and "action" (dict with params)."""

# 占位符: name, task, steps_summary
REACT_FINAL_ANSWER_PROMPT_TEMPLATE = """You are {name}. Generate final answer based on your reasoning chain.

Task: {task}
Reasoning chain:
{steps_summary}

Generate a comprehensive final answer as JSON."""
