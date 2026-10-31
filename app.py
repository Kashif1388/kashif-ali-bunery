"""
Resume -> Hostel Guide
Upload a resume and get a personalised explanation of the hostel:
what suits the person, what facilities matter to them, and the rules
they should know about. Built with Streamlit + Groq.
"""

import io
import os

import streamlit as st
from docx import Document
from groq import Groq
from pypdf import PdfReader

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
MODELS = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
MAX_RESUME_CHARS = 12000  # keeps the prompt well inside the model's context window

# Replace this with your real hostel details (or edit it live in the sidebar).
DEFAULT_HOSTEL_INFO = """\
Name: Green Valley Hostel
Location: 10 minutes walk from the main campus gate
Room types:
  - Single room: PKR 25,000/month, attached bathroom, study desk
  - Double sharing: PKR 15,000/month per person, shared bathroom
  - Dormitory (4 beds): PKR 9,000/month per person
Facilities: Wi-Fi (24/7), common study hall open until 2 AM, laundry, gym,
  mess (3 meals/day), prayer room, 24/7 security and CCTV, backup power
Rules: Gate closes at 11:00 PM, no guests in rooms (visitors lounge only),
  quiet hours 11 PM - 6 AM, no smoking, monthly rent due by the 5th
Mess timings: Breakfast 7-9, Lunch 1-3, Dinner 8-10
"""

SYSTEM_PROMPT = """You are a friendly hostel assistant. You are given a person's resume and
the official details of a hostel. Explain the hostel to this specific person.

Rules:
- Use ONLY the hostel details provided. If something is not mentioned, say it is not
  listed and suggest asking the hostel office. Never invent prices, rules or facilities.
- Use the resume only to personalise advice (field of study/work, schedule hints,
  interests, budget hints). Do not repeat sensitive personal data such as phone number,
  email or home address.
- Be concise, warm and practical."""

ANALYSIS_INSTRUCTIONS = """Write the answer in Markdown with these sections:
1. **About you (in brief)** - 2-3 lines on what the resume suggests (field, level, interests).
2. **About the hostel** - a short overview of the hostel.
3. **Best room option for you** - recommend one room type and explain why.
4. **Facilities that will matter to you** - 3-5 bullets tied to the resume.
5. **Rules to remember** - bullets.
6. **Questions to ask the hostel office** - 2-4 bullets about anything missing or unclear."""


# ----------------------------------------------------------------------------
# Helpers (no Streamlit calls in here, so they are easy to test)
# ----------------------------------------------------------------------------
def extract_text(file_bytes: bytes, filename: str) -> str:
    """Return plain text from a PDF, DOCX or TXT file. Raises ValueError on bad input."""
    name = filename.lower()
    try:
        if name.endswith(".pdf"):
            reader = PdfReader(io.BytesIO(file_bytes))
            if reader.is_encrypted:
                raise ValueError("This PDF is password protected.")
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
        elif name.endswith(".docx"):
            doc = Document(io.BytesIO(file_bytes))
            parts = [p.text for p in doc.paragraphs]
            for table in doc.tables:
                for row in table.rows:
                    parts.append(" | ".join(cell.text for cell in row.cells))
            text = "\n".join(parts)
        elif name.endswith(".txt"):
            text = file_bytes.decode("utf-8", errors="ignore")
        else:
            raise ValueError("Unsupported file type. Please upload a PDF, DOCX or TXT file.")
    except ValueError:
        raise
    except Exception as exc:  # corrupt files, odd encodings, etc.
        raise ValueError(f"Could not read the file: {exc}") from exc

    text = text.strip()
    if not text:
        raise ValueError(
            "No text found in the file. If it is a scanned image PDF, "
            "please upload a text-based PDF or a DOCX."
        )
    return text


def build_analysis_messages(resume_text: str, hostel_info: str) -> list:
    resume_text = resume_text[:MAX_RESUME_CHARS]
    user_content = (
        f"HOSTEL DETAILS:\n{hostel_info}\n\n"
        f"RESUME:\n{resume_text}\n\n"
        f"{ANALYSIS_INSTRUCTIONS}"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def build_followup_messages(resume_text: str, hostel_info: str, question: str) -> list:
    resume_text = resume_text[:MAX_RESUME_CHARS]
    user_content = (
        f"HOSTEL DETAILS:\n{hostel_info}\n\n"
        f"RESUME:\n{resume_text}\n\n"
        f"QUESTION: {question}\n\n"
        "Answer briefly, using only the hostel details above."
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def ask_groq(api_key: str, model: str, messages: list) -> str:
    """Call the Groq chat API and return the reply text."""
    client = Groq(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.3,
        max_tokens=1200,
    )
    content = response.choices[0].message.content
    return (content or "").strip()


def get_api_key(user_input: str) -> str:
    """Priority: sidebar input > Streamlit secrets > environment variable."""
    if user_input and user_input.strip():
        return user_input.strip()
    try:
        secret = st.secrets.get("GROQ_API_KEY", "")
        if secret:
            return str(secret).strip()
    except Exception:  # no secrets file present
        pass
    return os.environ.get("GROQ_API_KEY", "").strip()


# ----------------------------------------------------------------------------
# UI
# ----------------------------------------------------------------------------
def main():
    st.set_page_config(page_title="Resume to Hostel Guide", page_icon="🏠", layout="wide")
    st.title("🏠 Resume → Hostel Guide")
    st.caption("Upload your resume and get a personalised introduction to the hostel.")

    with st.sidebar:
        st.header("Settings")
        key_input = st.text_input(
            "Groq API key",
            type="password",
            help="Leave empty if the key is set in Streamlit secrets or GROQ_API_KEY.",
        )
        model = st.selectbox("Model", MODELS)
        st.divider()
        hostel_info = st.text_area(
            "Hostel details (edit to match your hostel)",
            value=DEFAULT_HOSTEL_INFO,
            height=320,
        )
        st.caption("The AI answers only from these details.")

    api_key = get_api_key(key_input)

    uploaded = st.file_uploader("Upload your resume", type=["pdf", "docx", "txt"])

    if uploaded is not None:
        try:
            resume_text = extract_text(uploaded.getvalue(), uploaded.name)
        except ValueError as err:
            st.error(str(err))
            return

        with st.expander("Extracted resume text"):
            st.text(resume_text[:3000] + ("..." if len(resume_text) > 3000 else ""))
        if len(resume_text) > MAX_RESUME_CHARS:
            st.info("Your resume is long, so only the first part will be used.")

        if st.button("Tell me about the hostel", type="primary"):
            if not api_key:
                st.error("Please enter your Groq API key in the sidebar.")
            elif not hostel_info.strip():
                st.error("Please fill in the hostel details in the sidebar.")
            else:
                with st.spinner("Analysing your resume..."):
                    try:
                        st.session_state["result"] = ask_groq(
                            api_key, model, build_analysis_messages(resume_text, hostel_info)
                        )
                    except Exception as exc:
                        st.session_state.pop("result", None)
                        st.error(f"Groq request failed: {exc}")

        if st.session_state.get("result"):
            st.markdown(st.session_state["result"])

            st.divider()
            question = st.text_input("Ask a follow-up question about the hostel")
            if st.button("Ask") and question.strip():
                if not api_key:
                    st.error("Please enter your Groq API key in the sidebar.")
                else:
                    with st.spinner("Thinking..."):
                        try:
                            answer = ask_groq(
                                api_key,
                                model,
                                build_followup_messages(resume_text, hostel_info, question.strip()),
                            )
                            st.markdown(answer)
                        except Exception as exc:
                            st.error(f"Groq request failed: {exc}")
    else:
        st.session_state.pop("result", None)
        st.info("👆 Upload a PDF, DOCX or TXT resume to get started.")

    st.caption("Your resume is sent to the Groq API for processing and is not stored by this app.")


if __name__ == "__main__":
    main()
