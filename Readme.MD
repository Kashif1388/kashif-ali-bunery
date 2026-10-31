# 🏠 Resume → Hostel Guide

Upload a resume (PDF, DOCX or TXT) and get a personalised introduction to your hostel:
a short profile of the person, the best room option for them, facilities that matter,
rules to remember, and questions to ask the hostel office. Built with **Streamlit** and the **Groq API**.

## Features
- Reads PDF, DOCX and TXT resumes
- Answers only from the hostel details you provide (no invented prices or rules)
- Follow-up questions about the hostel
- Choice of Groq models (`llama-3.3-70b-versatile`, `llama-3.1-8b-instant`)

## Run locally
```bash
pip install -r requirements.txt
export GROQ_API_KEY="your_key_here"      # Windows PowerShell: $env:GROQ_API_KEY="your_key_here"
streamlit run app.py
```
Or skip the variable and paste the key into the sidebar.

## Customise
Edit `DEFAULT_HOSTEL_INFO` at the top of `app.py` with your real hostel details
(rooms, prices, facilities, rules). Users can also edit it live in the sidebar.

## Deploy on Streamlit Community Cloud
1. Push this folder to a GitHub repo (`app.py`, `requirements.txt`, `README.md`).
2. Go to https://share.streamlit.io and sign in with GitHub.
3. Click **Create app**, choose the repo, branch `main`, main file `app.py`.
4. Open **Advanced settings → Secrets** and add:
   ```toml
   GROQ_API_KEY = "your_key_here"
   ```
5. Click **Deploy**.

## Privacy
Resumes are sent to the Groq API for processing and are not stored by this app.
Never commit your API key to GitHub.
