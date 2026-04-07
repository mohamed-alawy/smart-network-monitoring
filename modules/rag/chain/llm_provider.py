"""
LLM provider setup.
Switch between providers using PRIMARY_LLM env variable: gemini | openai
"""

import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

load_dotenv()


def get_llm():
    """Return LLM based on PRIMARY_LLM env variable (gemini | openai)."""
    provider = os.getenv("PRIMARY_LLM", "gemini").lower()

    if provider == "openai":
        return ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o"),
            api_key=os.getenv("OPENAI_API_KEY"),
            temperature=0.2,
            max_tokens=1024,
        )

    # default: gemini
    return ChatGoogleGenerativeAI(
        model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
        google_api_key=os.getenv("GEMINI_API_KEY"),
        temperature=0.2,
        max_output_tokens=1024,
    )
