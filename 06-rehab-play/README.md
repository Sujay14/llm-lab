# REHAB PLAY

A mobile-first, general rehabilitation companion for clinician-led care. It combines a patient-entered care plan, browser-local camera pose tracking with estimated repetition counts for selected movements, optional interactive activities, session check-ins, progress journaling and a local Ollama-based educational assistant.

## Important medical scope
This app is not a medical device, diagnostic tool, exercise-prescription engine, or substitute for a physiotherapist. It does not create or recommend treatment plans. Users enter only activities and dosage already provided by their own clinician. The mini activities are optional engagement tasks, not validated clinical assessments or treatment. The AI companion is constrained to general education, plain-language explanations and helping organize questions; it must not diagnose, prescribe, change dosage or recommend progression.

## Features
- Live camera pose tracking using MediaPipe Pose Landmarker in the browser
- Estimated rep counting for arm raises, squat / sit-to-stand patterns and standing knee raises
- Live pose skeleton overlay, movement phase feedback, session timer and local session log
- Add clinician-provided plan items and instructions
- Mark plan items complete for the day
- Optional target-tap coordination activity
- Optional visual attention matching activity
- Optional pattern recall activity
- Session mood check-in and optional notes
- Streaks based on active days, session and activity counts
- Local progress journal and JSON export
- Local Ollama assistant (default model qwen2.5:3b)
- Responsive mobile/tablet/desktop layout

## Run on Windows

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open on your computer: http://127.0.0.1:8000

## AI assistant
Start Ollama on the host computer. Check installed models:

```powershell
ollama list
```

The default is `qwen2.5:3b`. If not installed:

```powershell
ollama pull qwen2.5:3b
```

If you want to change model or Ollama URL, edit `.env` and restart Uvicorn.

## Open on phone / iPad
1. Connect computer and mobile device to the same Wi-Fi.
2. Find the computer's Wi-Fi IPv4 address using `ipconfig`.
3. Open `http://YOUR-PC-IP:8000` on the phone.
4. If Windows Firewall blocks it, allow inbound TCP port 8000 on your private network or ask the device administrator.

Camera access is requested only when the user presses Start camera. Camera video and pose landmarks are processed in the browser and are not uploaded or recorded by this app. MediaPipe assets are downloaded from their public CDN / model host. Browser camera access requires a secure context: use `http://127.0.0.1:8000` on the computer, or HTTPS when opening the app from a phone/iPad over the network. Plain `http://YOUR-PC-IP:8000` usually cannot access the camera on mobile browsers.

Rep counts are approximate computer-vision estimates, not validated clinical measurements. The thresholds are generic and may miss or double-count repetitions depending on camera angle, clothing, lighting, body visibility and movement style. Only use exercises and targets approved by the treating clinician. This is not a medical device or a substitute for supervision. The assistant requires the phone to reach FastAPI and the host computer to reach Ollama.

## Data and privacy
- Care plan items, completion records, check-ins, activity counts and streaks are saved in browser localStorage.
- Data remains in the browser on that device and does not sync across devices.
- Use Export my log to save a JSON copy.
- Messages sent to the AI companion are forwarded to the Ollama server configured on your host computer, not a hosted model provider by this application.
- Google Fonts are loaded from a CDN.
