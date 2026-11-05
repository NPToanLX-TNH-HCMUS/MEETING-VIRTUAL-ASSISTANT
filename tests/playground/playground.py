"""
Instead of directly test module in app.py, you can use this file.
All the changes in this file are ignored.
This file is also ignored when packaging.
"""

from src.backend.utils.llm import call_llm, parse_json_list


def main():
    res = call_llm(
        "what's time is it in Ho Chi Minh, Viet Nam ?", "google", "gemini-3.6-flash"
    )
    print(parse_json_list(str(res)))


if __name__ == "__main__":
    main()
