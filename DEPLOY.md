# Deploying ClinIQ — Vercel (frontend) + Render (backend)

This document summarizes a simple, reliable deployment using Vercel for the frontend and Render for the backend with a persistent disk for ChromaDB.

1) Frontend — Vercel
 - Push your repo to GitHub (or connect where your frontend lives).
 - On Vercel, create a new Project and import the repo. Choose the `cliniq-frontend` path if you only want the frontend.
 - Set Build & Output:
   - Framework: `Other` or `Vite`
   - Root Directory: `cliniq-frontend`
   - Build Command: `npm run build`
   - Output Directory: `dist`
 - Set Environment Variables (Vercel → Settings → Environment Variables):
   - `VITE_API_URL` = `https://api.YOUR_DOMAIN_OR_RENDER_URL` (point to Render service)
 - Deploy — Vercel will build the frontend and give you a URL. Optionally add a custom domain.

2) Backend — Render
 - Option A (recommended using Docker via Render UI or `render.yaml`):
   - Create a new Web Service on Render and connect your Git repo.
   - Choose Docker (we included `cliniq-backend/Dockerfile`).
   - Set Environment Variables in Render Dashboard (or via `render.yaml` runtime envVars):
       - `LLM_PROVIDER` = `openai` (recommended for Render)
       - `OPENAI_API_KEY` = `<your key>`
       - `CHROMA_PERSIST_DIR` = `/data/chroma_data` (matches `render.yaml` above)
   - Add a Persistent Disk (10GB suggested) and mount it to the service at `/data`.
   - Start the service. The internal container will run Uvicorn on port 8005.
 - Option B (if you prefer not to use Docker): create a Python service and set the start command to
   `uvicorn api:app --host 0.0.0.0 --port 8005` and configure build commands to `pip install -r requirements.txt`.

3) DNS and SSL
 - Point your domain's A record to the Render service or use Render's custom domain flow (Render handles HTTPS automatically).
 - For Vercel frontend, add your custom domain in Vercel and update DNS entries as instructed by Vercel.

4) Important considerations
 - LLM: Render cannot run local Ollama models — prefer `openai` or host an LLM on a separate VM/instance.
 - Persistence: Chroma DB files must be on a persistent disk. In Render, mount the persistent disk and set `CHROMA_PERSIST_DIR=/data/chroma_data`.
 - Secrets: store API keys as environment variables in Render & Vercel; never commit secrets.
 - CORS: update `cliniq-backend/api.py` to restrict `allow_origins` in production to your frontend URL.

5) Quick test after deploy
 - After Render finishes, set `VITE_API_URL` on Vercel to the Render URL (e.g. `https://cliniq-backend.onrender.com`).
 - Open the frontend URL and try uploading a document and querying.

If you want, I can:
- Add `CHROMA_PERSIST_DIR` support (done),
- Push `Dockerfile` (done) and `render.yaml` (done),
- Create a small `nginx` config for reverse proxy if you want to run a VM instead, or
- Help set Vercel environment variables and create the Render service interactively.
