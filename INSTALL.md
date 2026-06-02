# Installation

## Python Setup

Python 3.8 or newer is supported.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
```

Run the backend:

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Node Setup

Install Node.js 18 or newer.

```powershell
cd frontend
npm install
npm run dev
```

## FFmpeg Requirement

Mock ASR mode does not require FFmpeg.

Real speech recognition with faster-whisper usually needs FFmpeg available on your system path so uploaded audio formats such as WebM can be decoded.

## Optional Real ASR

```powershell
cd backend
pip install faster-whisper
```

Then set `ASR_MODE = "faster_whisper"` in `backend/app/config.py`.

## CPU-Only Notes

- Use smaller models such as `tiny`, `base`, or `small`.
- The prototype config uses `device="cpu"` and `compute_type="int8"`.
- First model download can take time.
- If the real ASR path fails, the app falls back to mock ASR.

## Troubleshooting

- Backend cannot import modules: run commands from the `backend` directory.
- Frontend cannot reach API: confirm backend is running at `http://127.0.0.1:8000`.
- Browser cannot record: use HTTPS or localhost/127.0.0.1, and grant microphone permission.
- WebM duration looks approximate: install FFmpeg and use real audio decoding in future extensions.
- Database state looks stale: stop servers and remove `data/app.db` to reseed from scratch.
