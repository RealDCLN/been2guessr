# Deploying on Render (free, step by step)

This is the recommended free setup: **GitHub for the code, Render for the
server**, with a free `https://<name>.onrender.com` address and automatic
deploys on every push.

> **Why not Netlify?** Netlify is excellent for static sites, but this app is a
> long-running FastAPI service. A 300-location build makes ~2,000 requests and
> takes 2–4 minutes; Netlify's synchronous functions time out in 10 seconds on
> the free plan. Netlify could host a landing page, but it cannot run the
> builder. Render's free Docker web service can.

## What you need

- A GitHub account (free)
- A Render account (free): <https://render.com>
- This repository on GitHub
- No credit card for the free tier in most regions

## 1. Personalise the links (optional, 1 minute)

The code works with the placeholders, but your public site should link to your
repo. Replace `your-username` with your GitHub username:

```bash
python scripts/personalize.py YOUR_GITHUB_USERNAME
```

This updates the README badges/clone URL, `pyproject.toml` links, the UI GitHub
links, and the user-agent string. Preview first with `--dry-run` if you like.

## 2. Push the repository to GitHub

Create an empty **public** repository named `been2guessr` at
<https://github.com/new>. Do **not** add a README, license, or `.gitignore`;
the repo already has them.

Then, from the project folder:

```bash
git init
git add .
git commit -m "Initial commit: been2guessr"
git branch -M main
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/been2guessr.git
git push -u origin main
```

If this folder is already a git repo (it is, with one commit), skip `git init`
and `git commit` and just add the remote and push:

```bash
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/been2guessr.git
git push -u origin main
```

Check that the repository is public and that `render.yaml` is at the root.

## 3. Deploy on Render

1. Sign in to <https://dashboard.render.com> with GitHub.
2. Click **New +** → **Blueprint**.
3. Connect your GitHub account if asked, then select `been2guessr`.
4. Render reads `render.yaml` and shows one service: `been2guessr`.
5. Click **Apply** / **Create**.
6. Wait for the Docker build. The first build takes 2–5 minutes.
7. When the status is **Live**, open the `onrender.com` URL.

Alternatively use the one-click button in the README (once the repo URL is
personalised).

### If the Blueprint is not detected

Create the service manually:

1. **New +** → **Web Service** → connect the repo.
2. Runtime: **Docker**.
3. Plan: **Free**.
4. Health check path: `/api/health`.
5. Add these environment variables:

   | Key | Value |
   | --- | --- |
   | `MAX_CONCURRENT_JOBS` | `1` |
   | `MAX_BUILD_LOCATIONS` | `1000` |
   | `RATE_LIMIT_JOBS` | `3` |
   | `JOB_TTL_SECONDS` | `3600` |
   | `TRUST_PROXY` | `true` |

6. Create the service. The container listens on Render's `PORT` automatically.

## 4. Test the site

Open your Render URL and:

1. Paste a public BeenEverywhere username, e.g. a friend's profile.
2. Ask for **20** locations first (faster than 300).
3. Watch the progress bar. A 20-location build usually finishes in under a
   minute once the instance is warm.
4. Download the JSON and import it into GeoGuessr via **Import locations**.

Check the API directly:

```bash
curl https://YOUR-SERVICE.onrender.com/api/health
# {"status":"ok","version":"0.1.0", ...}
```

## 5. Free-tier behaviour (important)

- **Spins down after ~15 minutes of inactivity.** The next visit takes
  30–60 seconds to wake up. The UI may look stuck for a moment; it is not.
- **One instance, one worker.** Jobs live in memory. Do not scale the service
  to multiple instances; downloads would land on the wrong worker.
- **A build needs the tab to stay open.** The UI polls every 1.2 seconds, which
  keeps the instance awake. If you close the tab for 15 minutes mid-build, the
  instance can sleep and the job is lost.
- **512 MB RAM.** That is enough for one 300-location build. Keep
  `MAX_CONCURRENT_JOBS=1`.
- **No persistent disk.** Finished JSON files expire after `JOB_TTL_SECONDS`
  (one hour). Download them before then.
- **Google may rate-limit datacenter IPs.** If most requests fail with 403,
  wait a few minutes, lower the count, or run the CLI locally for that build.

## 6. Custom domain (optional)

The `onrender.com` subdomain is free. A custom domain is also free to attach on
Render, but you must own the domain (Namecheap, Cloudflare, etc. — not free
unless you already have one).

1. Render dashboard → your service → **Settings** → **Custom Domains**.
2. Add `map.example.com`.
3. Create the CNAME record Render shows at your DNS provider.
4. Render issues a free TLS certificate automatically.

## 7. Updating the site

```bash
git add .
git commit -m "Update"
git push
```

Render redeploys automatically because `autoDeploy: true` is set in
`render.yaml`. You can also click **Manual Deploy** in the dashboard.

## 8. Troubleshooting

| Symptom | Fix |
| --- | --- |
| Build fails on `pip install` | Check the Render build log; make sure `pyproject.toml`, `README.md`, and `src/` are committed |
| Site loads but every build fails with 403 | Google is rate-limiting the instance; wait, lower the count, or use the CLI locally |
| "Job not found" after a while | The instance restarted or the TTL expired; rebuild |
| Page takes ~1 minute to load | Free instance woke from sleep; wait for the cold start |
| 502 after deploy | Check the service logs. The app must bind to `0.0.0.0` and `$PORT`; the Dockerfile already does |
| Out of memory | Keep `MAX_CONCURRENT_JOBS=1` and `MAX_BUILD_LOCATIONS=500` |
| Downloads disappear | They expire after one hour; download immediately or self-host |

## 9. Other free hosts

- **Koyeb** — one free Docker web service, scales to zero. Same setup: Docker,
  port from `PORT`, health check `/api/health`.
- **Hugging Face Spaces** — free Docker space; sleeps after long inactivity.
- **Fly.io / Railway** — no longer reliably free; may require a card.
- **Vercel / Netlify / Cloudflare Workers** — request/subrequest limits make
  them a poor fit for a build that makes thousands of outbound requests.

The app is a standard container, so any Docker host works.
