# 🏠 Resume → Hostel Allocation Card

Upload a student's resume (PDF, DOCX or TXT). The app uses the **Groq API** to read it and
builds a hostel allocation card with:

| Field | Where it comes from |
|---|---|
| Student name, university, department, semester, contact number, student profile | Extracted from the resume by AI (you can correct them) |
| Hostel name, warden name, room number, room capacity (3 or 4) | Your hostel records (sidebar) |
| Hostel fees (Paid / Unpaid) | Chosen by the admin (default: Unpaid) |

> A resume never contains hostel, room, warden or fee information, so the AI does **not** guess
> these. Only rooms with free beds can be selected. The card can be downloaded as JSON or CSV.

## Run locally
```bash
pip install -r requirements.txt
export GROQ_API_KEY="your_key_here"      # Windows PowerShell: $env:GROQ_API_KEY="your_key_here"
streamlit run app.py
```
Or paste the key into the sidebar instead.

## Set up your hostels
Edit `DEFAULT_HOSTELS` at the top of `app.py` (or edit the JSON in the sidebar under
**Hostel records (admin)**). Each hostel needs a `hostel_name`, `warden_name` and a list of
`rooms`. Each room needs a `room_number`, a `capacity` (3 or 4) and how many beds are `occupied`.

```json
{
  "hostel_name": "Green Valley Boys Hostel",
  "warden_name": "Mr. Imran Shah",
  "rooms": [{"room_number": "101", "capacity": 4, "occupied": 2}]
}
```
Room occupancy is not saved between sessions (the app has no database).

## Models
Default: `openai/gpt-oss-120b`. If a model is unavailable for your key, the app tries the others
automatically. Check https://console.groq.com/docs/models for current model names.

## Deploy on Streamlit Community Cloud
1. Upload `app.py`, `requirements.txt` and `README.md` to a GitHub repo (file names must match exactly).
2. Go to https://share.streamlit.io and sign in with GitHub.
3. Click **Create app**, pick the repo, branch `main`, main file `app.py`.
4. Open **Advanced settings → Secrets** and add:
   ```toml
   GROQ_API_KEY = "your_key_here"
   ```
5. Click **Deploy**.

## Privacy
Resumes are sent to the Groq API for processing and are not stored by this app.
Never commit your API key to GitHub.
