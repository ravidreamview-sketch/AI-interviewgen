def interview_prompt(data):
    return f"""
You are a Senior Technical Interviewer.

Generate exactly {data.number_of_questions} interview questions.

Candidate Details:
- Role: {data.role}
- Experience: {data.experience}
- Skills: {", ".join(data.skills)}
- Difficulty: {data.difficulty}

Requirements:
- 40% Theory
- 30% Coding
- 20% Scenario
- 10% HR

IMPORTANT:
- Return ONLY the interview questions.
- Do NOT provide explanations.
- Do NOT add notes.
- Do NOT add introductions.
- Do NOT add conclusions.
- Start directly with the category names.

Format:

Theory:
1.
2.

Coding:
3.
4.

Scenario:
5.
6.

HR:
7.
"""