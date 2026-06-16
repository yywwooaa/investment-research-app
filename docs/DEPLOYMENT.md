# Deployment Guide

This project can be shared publicly, but the public version should not depend on Bloomberg Desktop API. Bloomberg is meant for your local machine only, because Terminal/API access depends on your licensed session and entitlements.

## Recommended Public Demo

Use Render as a single Docker web service. This keeps the React frontend and FastAPI backend on one public URL and avoids CORS or split-hosting setup.

The included `Dockerfile`:

- builds the Vite frontend,
- installs the FastAPI backend requirements,
- serves `frontend/dist` through FastAPI,
- defaults to `VRW_DATA_SOURCE=yahoo`,
- writes temporary SQLite/cache files under `/tmp/variant-research-workbench`.

The included `render.yaml` sets the same public-demo environment variables and uses `/api/health` as the health check.

## What You Need To Do

1. Create a new GitHub repository.
2. Push this project folder to that repository. From this folder, the command-line version is:

```bash
git init
git add .
git commit -m "Initial Variant Research Workbench"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/variant-research-workbench.git
git push -u origin main
```

You can also do this through GitHub Desktop if that is more comfortable.

If `git push` says it cannot read a username, the machine is not authenticated with GitHub command-line git. The simplest fixes are:

- Install GitHub Desktop, sign in, add this local repository, and push.
- Install GitHub CLI, run `gh auth login`, then run `gh auth setup-git` and retry `git push -u origin main`.
- Configure an SSH key for GitHub, switch the remote to `git@github.com:YOUR_USERNAME/variant-research-workbench.git`, and retry the push.

Do not paste GitHub personal access tokens into the app or into AI chat.

3. Sign in to Render and choose **New > Blueprint** or **New > Web Service**.
4. Connect the GitHub repository.
5. If you use the Blueprint path, Render reads `render.yaml`.
6. If you create the service manually, choose Docker runtime and set:

```text
VRW_DATA_SOURCE=yahoo
VRW_LOCAL_DATA_DIR=/tmp/variant-research-workbench
VRW_SQLITE_PATH=/tmp/variant-research-workbench/workbench.sqlite3
```

7. Wait for the first build. The public app URL will look like:

```text
https://variant-research-workbench.onrender.com
```

## Vercel Option

Vercel is excellent for the Vite frontend. For this app, Vercel is less clean as the only host because the backend is Python/FastAPI, uses yfinance network calls, and has local SQLite-style persistence. A split deployment can work:

- Vercel hosts `frontend/`.
- Render hosts the FastAPI backend.
- The frontend points API requests at the Render URL.

For an interview portfolio link, the single Render Docker deploy is simpler and more faithful to the full app.

## Public Safety Checklist

Before pushing to GitHub:

- Keep `.env` untracked.
- Keep `data/local/` untracked.
- Do not commit SQLite databases, Bloomberg files, screenshots, or raw exports.
- Use `snapshot` or `yahoo` for public demos.
- Use `bloomberg` only on your local machine.

## Data Caveat For The Live Demo

Yahoo mode uses `yfinance`, which is unofficial and suitable for a portfolio/research demo, not institutional production data. The app should describe its recommendation output as a research signal for discussion, not investment advice.
