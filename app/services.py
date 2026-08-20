import os
import re
from dotenv import load_dotenv

load_dotenv()


def get_groq_client():
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY environment variable is not set. "
            "Please create a .env file with GROQ_API_KEY=your_key or set it in your environment."
        )
    from groq import Groq
    return Groq(api_key=api_key)


def generate_ai_questions(prompt: str) -> str:
    client = get_groq_client()
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )
    return response.choices[0].message.content


def parse_raw_questions(raw_text: str) -> list[str]:
    """
    Parses LLM output into a clean list of questions.
    Filters out category headers (e.g., 'Theory:', 'Coding:') and removes leading number prefixes.
    """
    if not raw_text:
        return []

    lines = raw_text.strip().split("\n")
    questions = []
    category_pattern = re.compile(r"^(#+\s*)?(theory|coding|scenario|hr|technical|behavioral|general|system design)\s*:?$", re.IGNORECASE)

    for line in lines:
        cleaned = line.strip()
        if not cleaned:
            continue

        # Skip category headers like 'Theory:', '### Coding:', '**HR:**'
        clean_header_check = re.sub(r"[\*\_#]", "", cleaned).strip()
        if category_pattern.match(clean_header_check):
            continue

        # Strip leading numbers/bullets e.g., '1. ', '1)', 'Q1:', '- '
        question_text = re.sub(r"^(q\d+[\.\:\)]|\d+[\.\:\)]|\-|\*)\s*", "", cleaned, flags=re.IGNORECASE).strip()
        # Clean any surrounding quotes or markdown asterisks
        question_text = re.sub(r"^\*\*(.*?)\*\*$", r"\1", question_text).strip()

        if len(question_text) > 5:
            questions.append(question_text)

    return questions