"""
Resume -> Hostel Allocation Card

The AI (Groq) reads an uploaded resume and extracts the student's details
(name, university, department, semester, contact number, profile).
Hostel details (hostel name, warden, room number, room capacity) come from your
hostel records, and the fee status (Paid / Unpaid) is chosen by the admin,
because none of these can be found in a resume. Nothing is invented by the AI.
"""

import csv
import io
import json
import os
import re

import streamlit as st
from docx import Document
from groq import Groq
from pypdf import PdfReader

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
# Groq lists the OpenAI GPT-OSS models as self-serve; the Llama models are
# "contact sales", so they may return a 404 on normal keys. The app falls back
# automatically to the next model if one is unavailable.
MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
]
MAX_RESUME_CHARS = 12000

STUDENT_FIELDS = [
    "student_name",
    "university_name",
    "department_name",
    "semester",
    "contact_number",
    "student_profile",
]
EMPTY_MARKERS = {"", "null", "none", "n/a", "na", "not found", "not available", "unknown", "-"}

# >>> Replace with your real hostels, wardens and rooms (or edit in the sidebar). <<<
DEFAULT_HOSTELS = [
    {
        "hostel_name": "Green Valley Boys Hostel",
        "warden_name": "Mr. Imran Shah",
        "warden_contact": "+92 300 1111111",
        "rooms": [
            {"room_number": "101", "capacity": 4, "occupied": 2},
            {"room_number": "102", "capacity": 3, "occupied": 3},
            {"room_number": "103", "capacity": 4, "occupied": 0},
            {"room_number": "201", "capacity": 3, "occupied": 1},
        ],
    },
    {
        "hostel_name": "Blue Hills Girls Hostel",
        "warden_name": "Mrs. Saima Khan",
        "warden_contact": "+92 300 2222222",
        "rooms": [
            {"room_number": "A-1", "capacity": 3, "occupied": 0},
            {"room_number": "A-2", "capacity": 4, "occupied": 4},
            {"room_number": "B-1", "capacity": 4, "occupied": 1},
        ],
    },
]

EXTRACT_SYSTEM_PROMPT = (
    "You extract information from resumes. "
    "Reply with a single JSON object and nothing else - no explanation, no markdown."
)
EXTRACT_INSTRUCTIONS = """Extract these keys from the resume below:
- student_name: full name of the student
- university_name: university or institute the person currently studies at
- department_name: department or program (e.g. Computer Science)
- semester: current semester if it is stated (e.g. "8th"); otherwise ""
- contact_number: the person's phone number
- student_profile: a 2-3 sentence summary in the third person (education, skills,
  projects, interests). Do not include phone number, email or address.

Rules: use ONLY what the resume states. If a value is not stated, use "". Do not guess.
Return exactly these six keys as JSON strings."""

FIELD_LABELS = [
    ("student_name", "Student name"),
    ("university_name", "University name"),
    ("department_name", "Department name"),
    ("semester", "Semester"),
    ("contact_number", "Contact number"),
    ("hostel_name", "Hostel name"),
    ("room_number", "Room number"),
    ("room_capacity", "Room capacity"),
    ("warden_name", "Warden name"),
    ("hostel_fees", "Hostel fees"),
    ("student_profile", "Student profile"),
]


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
    except Exception as exc:
        raise ValueError(f"Could not read the file: {exc}") from exc

    text = text.strip()
    if not text:
        raise ValueError(
            "No text found in the file. If it is a scanned image PDF, "
            "please upload a text-based PDF or a DOCX."
        )
    return text


def parse_json_response(text: str) -> dict:
    """Pull a JSON object out of a model reply (handles ```json fences and extra words)."""
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("The AI reply did not contain JSON.")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"The AI reply was not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("The AI reply was not a JSON object.")
    return data


def find_phone(text: str) -> str:
    """Fallback phone finder: first number-like string with 9-15 digits."""
    for match in re.finditer(r"\+?\d[\d\s\-()]{7,}\d", text):
        candidate = match.group(0).strip()
        digits = re.sub(r"\D", "", candidate)
        if 9 <= len(digits) <= 15:
            return candidate
    return ""


def clean_student_data(data: dict, resume_text: str) -> dict:
    """Keep only the expected keys as clean strings; fill the phone from the text if missing."""
    result = {}
    for key in STUDENT_FIELDS:
        value = data.get(key, "")
        if value is None or isinstance(value, (dict, list)):
            value = ""
        value = str(value).strip()
        result[key] = "" if value.lower() in EMPTY_MARKERS else value
    if not result["contact_number"]:
        result["contact_number"] = find_phone(resume_text)
    return result


def validate_hostels(data) -> list:
    """Check the hostel records and return them. Raises ValueError with a clear message."""
    if not isinstance(data, list) or not data:
        raise ValueError("Hostel records must be a non-empty list.")
    for i, hostel in enumerate(data, start=1):
        if not isinstance(hostel, dict):
            raise ValueError(f"Hostel #{i} must be an object.")
        for key in ("hostel_name", "warden_name"):
            if not str(hostel.get(key, "")).strip():
                raise ValueError(f"Hostel #{i} is missing '{key}'.")
        rooms = hostel.get("rooms")
        if not isinstance(rooms, list) or not rooms:
            raise ValueError(f"Hostel '{hostel['hostel_name']}' needs a non-empty 'rooms' list.")
        for room in rooms:
            if not isinstance(room, dict) or not str(room.get("room_number", "")).strip():
                raise ValueError(f"A room in '{hostel['hostel_name']}' has no room_number.")
            cap, occ = room.get("capacity"), room.get("occupied", 0)
            if cap not in (3, 4) or isinstance(cap, bool):
                raise ValueError(f"Room {room['room_number']}: capacity must be 3 or 4.")
            if not isinstance(occ, int) or isinstance(occ, bool) or not 0 <= occ <= cap:
                raise ValueError(f"Room {room['room_number']}: 'occupied' must be 0 to {cap}.")
    return data


def available_rooms(hostel: dict) -> list:
    """Rooms that still have at least one free bed."""
    return [r for r in hostel["rooms"] if r["occupied"] < r["capacity"]]


def room_label(room: dict) -> str:
    free = room["capacity"] - room["occupied"]
    return f"{room['room_number']}  (capacity {room['capacity']}, {free} bed{'s' if free != 1 else ''} free)"


def build_record(student: dict, hostel: dict, room: dict, fee_status: str) -> dict:
    """Combine everything into the final card (in display order)."""
    return {
        "student_name": student["student_name"],
        "university_name": student["university_name"],
        "department_name": student["department_name"],
        "semester": student["semester"],
        "contact_number": student["contact_number"],
        "hostel_name": hostel["hostel_name"],
        "room_number": str(room["room_number"]),
        "room_capacity": int(room["capacity"]),
        "warden_name": hostel["warden_name"],
        "hostel_fees": fee_status,
        "student_profile": student["student_profile"],
    }


def record_to_csv(record: dict) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(record.keys())
    writer.writerow(record.values())
    return buf.getvalue()


def ask_groq(api_key: str, model: str, messages: list, temperature: float = 0.0) -> str:
    """Call the Groq chat API. If a model is unavailable (404), the next one is tried."""
    client = Groq(api_key=api_key)
    candidates = [model] + [m for m in MODELS if m != model]
    last_error = None
    for name in candidates:
        try:
            response = client.chat.completions.create(
                model=name,
                messages=messages,
                temperature=temperature,
                max_tokens=4000,  # reasoning models spend part of this on thinking
            )
        except Exception as exc:
            text = str(exc).lower()
            if "model_not_found" in text or "does not exist" in text or "404" in text:
                last_error = exc
                continue
            raise
        content = (response.choices[0].message.content or "").strip()
        if content:
            return content
        last_error = RuntimeError(f"Model {name} returned an empty reply.")
    raise RuntimeError(f"No available Groq model worked. Last error: {last_error}")


def extract_student_details(api_key: str, model: str, resume_text: str) -> dict:
    resume_text = resume_text[:MAX_RESUME_CHARS]
    messages = [
        {"role": "system", "content": EXTRACT_SYSTEM_PROMPT},
        {"role": "user", "content": f"{EXTRACT_INSTRUCTIONS}\n\nRESUME:\n{resume_text}"},
    ]
    reply = ask_groq(api_key, model, messages)
    return clean_student_data(parse_json_response(reply), resume_text)


def get_api_key(user_input: str) -> str:
    """Priority: sidebar input > Streamlit secrets > environment variable."""
    if user_input and user_input.strip():
        return user_input.strip()
    try:
        secret = st.secrets.get("GROQ_API_KEY", "")
        if secret:
            return str(secret).strip()
    except Exception:
        pass
    return os.environ.get("GROQ_API_KEY", "").strip()


# ----------------------------------------------------------------------------
# UI
# ----------------------------------------------------------------------------
def main():
    st.set_page_config(page_title="Hostel Allocation Card", page_icon="🏠", layout="wide")
    st.title("🏠 Resume → Hostel Allocation Card")
    st.caption("Upload a resume. The AI fills in the student details; you pick the room and fee status.")

    # ---- Sidebar -----------------------------------------------------------
    with st.sidebar:
        st.header("Settings")
        key_input = st.text_input(
            "Groq API key",
            type="password",
            help="Leave empty if the key is set in Streamlit secrets or GROQ_API_KEY.",
        )
        model = st.selectbox("Model", MODELS)
        st.divider()
        with st.expander("Hostel records (admin)"):
            st.caption("Edit hostels, wardens and rooms. Room capacity must be 3 or 4.")
            hostels_text = st.text_area(
                "Hostel records (JSON)",
                value=json.dumps(DEFAULT_HOSTELS, indent=2),
                height=350,
            )

    try:
        hostels = validate_hostels(json.loads(hostels_text))
    except (ValueError, json.JSONDecodeError) as err:
        st.sidebar.error(f"Hostel records problem: {err}. Using the built-in records instead.")
        hostels = DEFAULT_HOSTELS

    api_key = get_api_key(key_input)

    # ---- Step 1: upload ----------------------------------------------------
    st.subheader("1. Upload resume")
    uploaded = st.file_uploader("PDF, DOCX or TXT", type=["pdf", "docx", "txt"])
    if uploaded is None:
        st.info("👆 Upload a resume to get started.")
        return

    try:
        resume_text = extract_text(uploaded.getvalue(), uploaded.name)
    except ValueError as err:
        st.error(str(err))
        return

    # Reset the form when a different file is uploaded.
    file_id = f"{uploaded.name}:{len(uploaded.getvalue())}"
    if st.session_state.get("file_id") != file_id or "f_student_name" not in st.session_state:
        st.session_state["file_id"] = file_id
        for field in STUDENT_FIELDS:
            st.session_state[f"f_{field}"] = ""

    with st.expander("Extracted resume text"):
        st.text(resume_text[:3000] + ("..." if len(resume_text) > 3000 else ""))
    if len(resume_text) > MAX_RESUME_CHARS:
        st.info("The resume is long, so only the first part is used.")

    # ---- Step 2: AI extraction ---------------------------------------------
    st.subheader("2. Extract student details")
    if st.button("Extract details with AI", type="primary"):
        if not api_key:
            st.error("Please enter your Groq API key in the sidebar.")
        else:
            with st.spinner("Reading the resume..."):
                try:
                    details = extract_student_details(api_key, model, resume_text)
                    for field in STUDENT_FIELDS:
                        st.session_state[f"f_{field}"] = details[field]
                    st.success("Done. Please check the details below and correct anything wrong.")
                except Exception as exc:
                    st.error(f"Extraction failed: {exc}")

    col1, col2 = st.columns(2)
    with col1:
        st.text_input("Student name", key="f_student_name")
        st.text_input("University name", key="f_university_name")
        st.text_input("Department name", key="f_department_name")
    with col2:
        st.text_input("Semester", key="f_semester")
        st.text_input("Contact number", key="f_contact_number")
    st.text_area("Student profile", key="f_student_profile", height=110)

    # ---- Step 3: hostel details --------------------------------------------
    st.subheader("3. Hostel details")
    hostel_names = [h["hostel_name"] for h in hostels]
    hostel = hostels[hostel_names.index(st.selectbox("Hostel", hostel_names))]
    rooms = available_rooms(hostel)

    c1, c2 = st.columns(2)
    with c1:
        if rooms:
            room = rooms[[room_label(r) for r in rooms].index(
                st.selectbox("Room (only rooms with free beds)", [room_label(r) for r in rooms])
            )]
        else:
            room = None
            st.warning("This hostel has no free beds. Choose another hostel.")
    with c2:
        fee_status = st.radio(
            "Hostel fees", ["Unpaid", "Paid"], horizontal=True,
            help="Fee status is not in a resume, so the admin sets it here.",
        )
    st.caption(f"Warden: {hostel['warden_name']}")

    # ---- Step 4: final card ------------------------------------------------
    st.subheader("4. Allocation card")
    student = {f: st.session_state.get(f"f_{f}", "").strip() for f in STUDENT_FIELDS}
    if room is None:
        return
    record = build_record(student, hostel, room, fee_status)

    missing = [label for key, label in FIELD_LABELS if record[key] in ("", None)]
    if missing:
        st.warning("Still empty: " + ", ".join(missing) + ". Fill them in above if you can.")

    with st.container(border=True):
        for key, label in FIELD_LABELS:
            value = record[key] if record[key] not in ("", None) else "—"
            st.markdown(f"**{label}:** {value}")

    d1, d2 = st.columns(2)
    d1.download_button(
        "Download JSON", json.dumps(record, indent=2, ensure_ascii=False),
        file_name="hostel_card.json", mime="application/json",
    )
    d2.download_button(
        "Download CSV", record_to_csv(record), file_name="hostel_card.csv", mime="text/csv",
    )
    st.caption(
        "Your resume is sent to the Groq API for processing and is not stored by this app. "
        "Room occupancy is not saved between sessions."
    )


if __name__ == "__main__":
    main()
