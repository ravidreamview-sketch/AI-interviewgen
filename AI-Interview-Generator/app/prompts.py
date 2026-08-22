def interview_prompt(data):
    role_str = (data.role or "").strip()
    role_lower = role_str.lower()
    skills_str = ", ".join(data.skills or [])
    exp = data.experience or "3-5 Years"
    diff = data.difficulty or "Medium"
    num_q = data.number_of_questions or 5
    custom_q = getattr(data, "custom_question", None) or ""

    seed_instruction = ""
    if custom_q.strip():
        seed_instruction = f"""
SPECIFIC SEED / FOCUS TOPIC:
"{custom_q.strip()}"
STRICT REQUIREMENT: Ensure all generated questions directly probe, expand, and branch from this specific topic into deep-dive scenarios, trade-offs, architecture, and edge cases.
"""

    format_instruction = f"""
CRITICAL COUNT & OUTPUT FORMAT:
- You MUST generate EXACTLY {num_q} interview questions (numbered sequentially from 1 to {num_q}).
- Return ONLY the numbered list of {num_q} questions.
- Do NOT output any introductory text, section headers, category labels (e.g., do not write 'User Research:' or 'Coding:'), markdown formatting asterisks around the whole question, or concluding notes.
- Format every question on its own line:
1. [First question text]
2. [Second question text]
...
{num_q}. [{num_q}th question text]
"""

    if any(k in role_lower for k in ["ux designer", "user experience designer", "ux researcher", "interaction designer"]) and "product" not in role_lower and "ui/ux" not in role_lower:
        return f"""
You are the Head of UX & Design Research conducting a rigorous, role-specific interview for a {role_str} position ({exp}, Level: {diff}, Skills: {skills_str}).

Generate exactly {num_q} interview questions strictly relevant to UX Design.
{seed_instruction}
{format_instruction}
"""
    elif "product designer" in role_lower:
        return f"""
You are the VP of Product Design interviewing a {role_str} ({exp}, Level: {diff}, Skills: {skills_str}).

Generate exactly {num_q} interview questions strictly relevant to Product Design.
{seed_instruction}
{format_instruction}
"""
    elif "ui/ux" in role_lower or "ui designer" in role_lower or "visual" in role_lower:
        return f"""
You are a Principal UI/UX & Interaction Design Director interviewing a {role_str} ({exp}, Level: {diff}, Skills: {skills_str}).

Generate exactly {num_q} interview questions strictly focused on UI/UX Design.
{seed_instruction}
{format_instruction}
"""
    elif "front" in role_lower or "react" in role_lower:
        return f"""
You are a Principal Frontend Architect interviewing a {role_str} ({exp}, Level: {diff}, Skills: {skills_str}).

Generate exactly {num_q} interview questions strictly focused on Modern Frontend Engineering.
{seed_instruction}
{format_instruction}
"""
    elif "back" in role_lower or "python" in role_lower or "fastapi" in role_lower:
        return f"""
You are a Principal Backend & Systems Architect interviewing a {role_str} ({exp}, Level: {diff}, Skills: {skills_str}).

Generate exactly {num_q} interview questions strictly focused on Backend Engineering and Distributed Systems.
{seed_instruction}
{format_instruction}
"""
    elif "genai" in role_lower or "ai" in role_lower or "llm" in role_lower:
        return f"""
You are a Chief AI Architect interviewing a {role_str} ({exp}, Level: {diff}, Skills: {skills_str}).

Generate exactly {num_q} interview questions strictly focused on Generative AI, LLMs, and AI Systems.
{seed_instruction}
{format_instruction}
"""
    else:
        return f"""
You are a Principal Hiring Manager and Senior Interviewer conducting a specialized interview for a {role_str} ({exp}, Level: {diff}, Skills: {skills_str}).

Generate exactly {num_q} interview questions strictly tailored to the responsibilities, tools, and technical nuances of {role_str}.
{seed_instruction}
{format_instruction}
"""