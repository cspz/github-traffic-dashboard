import os
import sqlite3
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("GITHUB_TOKEN")
USERNAME = os.getenv("GITHUB_USERNAME")
DB_PATH = "traffic.db"

HEADERS = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github+json",
}


def get_public_repos():
    repos = []
    page = 1
    while True:
        url = f"https://api.github.com/user/repos?type=public&per_page=100&page={page}"
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        batch = response.json()
        if not batch:
            break
        repos.extend([r["name"] for r in batch])
        page += 1
    return repos


def get_views(repo):
    url = f"https://api.github.com/repos/{USERNAME}/{repo}/traffic/views"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 403:
        print(f"  [views] No access for {repo}, skipping.")
        return []
    response.raise_for_status()
    return response.json().get("views", [])


def get_clones(repo):
    url = f"https://api.github.com/repos/{USERNAME}/{repo}/traffic/clones"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 403:
        print(f"  [clones] No access for {repo}, skipping.")
        return []
    response.raise_for_status()
    return response.json().get("clones", [])


def get_referrers(repo):
    url = f"https://api.github.com/repos/{USERNAME}/{repo}/traffic/popular/referrers"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 403:
        print(f"  [referrers] No access for {repo}, skipping.")
        return []
    response.raise_for_status()
    return response.json()


def init_db(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS views (
            repo        TEXT NOT NULL,
            date        TEXT NOT NULL,
            views       INTEGER NOT NULL,
            uniques     INTEGER NOT NULL,
            PRIMARY KEY (repo, date)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS clones (
            repo        TEXT NOT NULL,
            date        TEXT NOT NULL,
            clones      INTEGER NOT NULL,
            uniques     INTEGER NOT NULL,
            PRIMARY KEY (repo, date)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS referrers (
            repo        TEXT NOT NULL,
            fetched_at  TEXT NOT NULL,
            referrer    TEXT NOT NULL,
            count       INTEGER NOT NULL,
            uniques     INTEGER NOT NULL,
            PRIMARY KEY (repo, fetched_at, referrer)
        )
    """)
    conn.commit()


def upsert_views(conn, repo, views):
    for entry in views:
        date = entry["timestamp"][:10]
        conn.execute("""
            INSERT INTO views (repo, date, views, uniques)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(repo, date) DO UPDATE SET
                views   = excluded.views,
                uniques = excluded.uniques
        """, (repo, date, entry["count"], entry["uniques"]))
    conn.commit()


def upsert_clones(conn, repo, clones):
    for entry in clones:
        date = entry["timestamp"][:10]
        conn.execute("""
            INSERT INTO clones (repo, date, clones, uniques)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(repo, date) DO UPDATE SET
                clones  = excluded.clones,
                uniques = excluded.uniques
        """, (repo, date, entry["count"], entry["uniques"]))
    conn.commit()


def upsert_referrers(conn, repo, referrers):
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for entry in referrers:
        conn.execute("""
            INSERT INTO referrers (repo, fetched_at, referrer, count, uniques)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(repo, fetched_at, referrer) DO UPDATE SET
                count   = excluded.count,
                uniques = excluded.uniques
        """, (repo, fetched_at, entry["referrer"], entry["count"], entry["uniques"]))
    conn.commit()


def main():
    print(f"Connecting to DB: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    print(f"Fetching public repos for {USERNAME}...")
    repos = get_public_repos()
    print(f"Found {len(repos)} repos: {repos}\n")

    for repo in repos:
        print(f"Processing: {repo}")

        views = get_views(repo)
        upsert_views(conn, repo, views)
        print(f"  views: {len(views)} entries")

        clones = get_clones(repo)
        upsert_clones(conn, repo, clones)
        print(f"  clones: {len(clones)} entries")

        referrers = get_referrers(repo)
        upsert_referrers(conn, repo, referrers)
        print(f"  referrers: {len(referrers)} entries")

    conn.close()
    print("\nDone. DB updated.")


if __name__ == "__main__":
    main()
