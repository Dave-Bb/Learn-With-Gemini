# Learn With Gemini — Cloud Deployment Guide

## Quick Reference

| Item | Value |
|---|---|
| GCP Project | `learn-with-gemini-2026` |
| Cloud Run Service | `learn-with-gemini-vision` |
| Region | `us-central1` |
| Service URL | `https://learn-with-gemini-vision-740218009940.us-central1.run.app` |
| Console | https://console.cloud.google.com/run?project=learn-with-gemini-2026 |

---

## How to Redeploy After Code Changes

If you edit anything in `cloud/main.py`, redeploy with:

```
cd cloud
gcloud run deploy learn-with-gemini-vision --source . --region us-central1 --project learn-with-gemini-2026 --allow-unauthenticated --set-env-vars="GOOGLE_API_KEY=<your-key>" --memory=512Mi
```

Or just run `deploy.bat` from the project root (it reads the key from `.env`).

Verify it worked:
```
curl https://learn-with-gemini-vision-740218009940.us-central1.run.app/
```

Should return: `{"status":"ok","service":"Learn With Gemini Vision Service","model":"gemini-2.5-flash"}`

---

## How to Update the API Key on Cloud Run

If you regenerate your API key:

1. Update `.env` locally
2. Update the Cloud Run env var:
```
gcloud run services update learn-with-gemini-vision --region us-central1 --project learn-with-gemini-2026 --set-env-vars="GOOGLE_API_KEY=<new-key>"
```

---

## How to Check Logs

Terminal:
```
gcloud run services logs read learn-with-gemini-vision --region us-central1 --project learn-with-gemini-2026 --limit=50
```

Browser:
https://console.cloud.google.com/run/detail/us-central1/learn-with-gemini-vision/logs?project=learn-with-gemini-2026

---

## Recording the Proof-of-Deployment Video

The hackathon requires a short screen recording proving the backend runs on Google Cloud. Here's a script:

### What to show (30-60 seconds)

1. **Open the Cloud Run console**
   - Go to: https://console.cloud.google.com/run/detail/us-central1/learn-with-gemini-vision/metrics?project=learn-with-gemini-2026
   - Show the service name, region, URL, and "green checkmark" status

2. **Show the Logs tab**
   - Click "Logs" tab in the Cloud Run console
   - Show live request logs (POST /generate-plan, /find-element, /analyze-screen)
   - If no logs yet, trigger some by running the app or curling the endpoint

3. **Hit the health endpoint live**
   - Open a browser tab to `https://learn-with-gemini-vision-740218009940.us-central1.run.app/`
   - Show the JSON response proving it's live

4. **Optional: show the deploy script**
   - Open `deploy.bat` in the repo to prove automated deployment

### How to trigger logs for the recording

Run this in a terminal while recording to generate visible Cloud Run traffic:

```
curl -s https://learn-with-gemini-vision-740218009940.us-central1.run.app/
curl -s -X POST https://learn-with-gemini-vision-740218009940.us-central1.run.app/generate-plan -H "Content-Type: application/json" -d "{\"topic\": \"Python Hello World\"}"
```

Then switch to the Logs tab — you'll see the requests appear.

---

## Architecture (for submission)

```
Desktop Client (PyQt6)              Google Cloud (learn-with-gemini-2026)
+---------------------+             +----------------------------------+
|                     |             |                                  |
|  learn_with_gemini.py |           |  Cloud Run: learn-with-gemini-vision   |
|  session.py         |             |  +----------------------------+  |
|  overlay.py         |             |  | POST /generate-plan        |  |
|  audio.py           |   HTTPS     |  | POST /find-element         |  |
|                     +------------>|  | POST /analyze-screen       |  |
|  Vision requests    |             |  |                            |  |
|                     |             |  | Calls Gemini Vision API    |  |
|                     |             |  +----------------------------+  |
|                     |             |                                  |
|  Live API audio  +--------------->|  Gemini Live API (WebSocket)     |
|  (direct stream)    |             |  Audio model for conversation    |
+---------------------+             +----------------------------------+
```

---

## Costs

Cloud Run charges per request + compute time. With the free tier (2 million requests/month), this project costs essentially nothing during development and demos.
