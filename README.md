# github-traffic-dashboard

A lightweight tool that fetches traffic data from the GitHub API across all your public repositories, persists it locally in SQLite, and renders an interactive dashboard using Plotly.

GitHub's API only exposes a 14-day rolling window of traffic data. By running the fetch script daily via GitHub Actions and committing the updated database back to the repo, this tool accumulates historical data indefinitely.

---

## Features

- Fetches views, unique visitors, clones, and referrers for all public repos
- Persists data in SQLite with upsert logic — no duplicates, safe to run multiple times
- Interactive HTML dashboard with per-repo charts and a summary table
- GitHub Actions workflow runs daily and commits the updated database automatically
- No external services, no servers, no cost

---

## Project Structure

```
github-traffic-dashboard/
├── .github/
│   └── workflows/
│       └── fetch.yml       # daily GitHub Actions workflow
├── fetch.py                # pulls data from GitHub API → writes to SQLite
├── dashboard.py            # reads SQLite → generates Plotly HTML dashboard
├── traffic.db              # persisted traffic data (committed to repo)
├── requirements.txt
├── .env                    # local secrets (not committed)
└── .gitignore
```

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/your-username/github-traffic-dashboard.git
cd github-traffic-dashboard
```

### 2. Create a virtual environment and install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Create a `.env` file

```
GITHUB_TOKEN=your_personal_access_token
GITHUB_USERNAME=your_github_username
```

Generate a Personal Access Token at GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic). Only the `public_repo` scope is required.

### 4. Run the fetch script

```bash
python3 fetch.py
```

This creates `traffic.db` and populates it with the last 14 days of data for all your public repos.

### 5. Open the dashboard

```bash
python3 dashboard.py
```

This generates `dashboard.html` and opens it in your browser.

---

## GitHub Actions — Automatic Daily Fetch

The workflow in `.github/workflows/fetch.yml` runs `fetch.py` every day at 8am UTC and commits the updated `traffic.db` back to the repo.

### Setup

1. Go to your repo → Settings → Actions → General → Workflow permissions → select **Read and write permissions**
2. Go to Settings → Secrets and variables → Actions and add two secrets:
   - `GH_TOKEN` — your GitHub Personal Access Token
   - `GH_USERNAME` — your GitHub username

Once configured, the workflow runs automatically. You can also trigger it manually from the Actions tab.

### Local workflow after setup

```bash
git pull              # get the latest traffic.db committed by Actions
python3 dashboard.py  # open the dashboard
```

---

## Dashboard

The generated `dashboard.html` includes:

- Views and unique visitors over time per repo
- Clones and unique cloners over time per repo
- Top referrers aggregated across all repos
- Summary table with totals per repo

`dashboard.html` is excluded from git — it is generated locally on demand.

---

## Requirements

- Python 3.9+
- `requests`
- `python-dotenv`
- `plotly`