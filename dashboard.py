import sqlite3
import webbrowser
import os
from datetime import datetime
import plotly.graph_objects as go
from plotly.subplots import make_subplots

DB_PATH = "traffic.db"
OUTPUT_HTML = "dashboard.html"


def load_views(conn):
    cursor = conn.execute("""
        SELECT repo, date, views, uniques
        FROM views
        ORDER BY repo, date
    """)
    data = {}
    for repo, date, views, uniques in cursor.fetchall():
        if repo not in data:
            data[repo] = {"dates": [], "views": [], "uniques": []}
        data[repo]["dates"].append(date)
        data[repo]["views"].append(views)
        data[repo]["uniques"].append(uniques)
    return data


def load_clones(conn):
    cursor = conn.execute("""
        SELECT repo, date, clones, uniques
        FROM clones
        ORDER BY repo, date
    """)
    data = {}
    for repo, date, clones, uniques in cursor.fetchall():
        if repo not in data:
            data[repo] = {"dates": [], "clones": [], "uniques": []}
        data[repo]["dates"].append(date)
        data[repo]["clones"].append(clones)
        data[repo]["uniques"].append(uniques)
    return data


def load_referrers(conn):
    cursor = conn.execute("""
        SELECT repo, referrer, SUM(count) as total, SUM(uniques) as total_uniques
        FROM referrers
        GROUP BY repo, referrer
        ORDER BY repo, total DESC
    """)
    data = {}
    for repo, referrer, total, total_uniques in cursor.fetchall():
        if repo not in data:
            data[repo] = {"referrers": [], "counts": [], "uniques": []}
        data[repo]["referrers"].append(referrer)
        data[repo]["counts"].append(total)
        data[repo]["uniques"].append(total_uniques)
    return data


def build_dashboard(views_data, clones_data, referrers_data):
    repos = sorted(views_data.keys())
    colors_views   = "#4C9BE8"
    colors_uniques = "#E8A24C"
    colors_clones  = "#4CE8A2"

    sections = []

    # ── Per-repo views + unique visitors ────────────────────────────────────
    for repo in repos:
        v = views_data.get(repo, {"dates": [], "views": [], "uniques": []})
        fig = make_subplots(specs=[[{"secondary_y": False}]])

        fig.add_trace(go.Bar(
            x=v["dates"], y=v["views"],
            name="Views", marker_color=colors_views,
            opacity=0.85
        ))
        fig.add_trace(go.Scatter(
            x=v["dates"], y=v["uniques"],
            name="Unique visitors", mode="lines+markers",
            line=dict(color=colors_uniques, width=2),
            marker=dict(size=6)
        ))

        fig.update_layout(
            title=f"{repo} — Views & Unique Visitors",
            xaxis_title="Date",
            yaxis_title="Count",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            plot_bgcolor="#1e1e2e",
            paper_bgcolor="#1e1e2e",
            font=dict(color="#cdd6f4"),
            hovermode="x unified",
            margin=dict(t=60, b=40, l=50, r=20),
            height=350,
        )
        fig.update_xaxes(gridcolor="#313244")
        fig.update_yaxes(gridcolor="#313244")

        sections.append(fig.to_html(full_html=False, include_plotlyjs=False))

    # ── Per-repo clones ──────────────────────────────────────────────────────
    for repo in repos:
        c = clones_data.get(repo, {"dates": [], "clones": [], "uniques": []})
        fig = go.Figure()

        fig.add_trace(go.Bar(
            x=c["dates"], y=c["clones"],
            name="Clones", marker_color=colors_clones,
            opacity=0.85
        ))
        fig.add_trace(go.Scatter(
            x=c["dates"], y=c["uniques"],
            name="Unique cloners", mode="lines+markers",
            line=dict(color=colors_uniques, width=2),
            marker=dict(size=6)
        ))

        fig.update_layout(
            title=f"{repo} — Clones & Unique Cloners",
            xaxis_title="Date",
            yaxis_title="Count",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            plot_bgcolor="#1e1e2e",
            paper_bgcolor="#1e1e2e",
            font=dict(color="#cdd6f4"),
            hovermode="x unified",
            margin=dict(t=60, b=40, l=50, r=20),
            height=350,
        )
        fig.update_xaxes(gridcolor="#313244")
        fig.update_yaxes(gridcolor="#313244")

        sections.append(fig.to_html(full_html=False, include_plotlyjs=False))

    # ── Top referrers (all repos combined) ──────────────────────────────────
    all_referrers = {}
    for repo, rdata in referrers_data.items():
        for ref, count, uniq in zip(rdata["referrers"], rdata["counts"], rdata["uniques"]):
            if ref not in all_referrers:
                all_referrers[ref] = {"count": 0, "uniques": 0}
            all_referrers[ref]["count"]   += count
            all_referrers[ref]["uniques"] += uniq

    if all_referrers:
        sorted_refs = sorted(all_referrers.items(), key=lambda x: x[1]["count"], reverse=True)[:15]
        ref_names  = [r[0] for r in sorted_refs]
        ref_counts = [r[1]["count"] for r in sorted_refs]

        fig = go.Figure(go.Bar(
            x=ref_counts, y=ref_names,
            orientation="h",
            marker_color=colors_views,
            opacity=0.85
        ))
        fig.update_layout(
            title="Top Referrers (all repos)",
            xaxis_title="Total views",
            yaxis=dict(autorange="reversed"),
            plot_bgcolor="#1e1e2e",
            paper_bgcolor="#1e1e2e",
            font=dict(color="#cdd6f4"),
            margin=dict(t=60, b=40, l=160, r=20),
            height=max(300, len(ref_names) * 35),
        )
        fig.update_xaxes(gridcolor="#313244")
        fig.update_yaxes(gridcolor="#313244")

        sections.append(fig.to_html(full_html=False, include_plotlyjs=False))

    # ── Summary table ────────────────────────────────────────────────────────
    summary_rows = ""
    for repo in repos:
        total_views   = sum(views_data.get(repo, {}).get("views", []))
        total_uniques = sum(views_data.get(repo, {}).get("uniques", []))
        total_clones  = sum(clones_data.get(repo, {}).get("clones", []))
        summary_rows += f"""
        <tr>
            <td>{repo}</td>
            <td>{total_views}</td>
            <td>{total_uniques}</td>
            <td>{total_clones}</td>
        </tr>"""

    summary_table = f"""
    <div class="summary">
        <h2>Summary (all time)</h2>
        <table>
            <thead>
                <tr>
                    <th>Repo</th>
                    <th>Total Views</th>
                    <th>Total Unique Visitors</th>
                    <th>Total Clones</th>
                </tr>
            </thead>
            <tbody>{summary_rows}</tbody>
        </table>
    </div>
    """

    # ── Assemble HTML ────────────────────────────────────────────────────────
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    charts_html = "\n".join(f'<div class="chart">{s}</div>' for s in sections)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GitHub Traffic Dashboard</title>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background: #11111b;
            color: #cdd6f4;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            padding: 32px 24px;
        }}
        h1 {{
            font-size: 1.6rem;
            margin-bottom: 4px;
            color: #cba6f7;
        }}
        .subtitle {{
            font-size: 0.85rem;
            color: #6c7086;
            margin-bottom: 32px;
        }}
        h2 {{
            font-size: 1.1rem;
            margin-bottom: 16px;
            color: #89b4fa;
        }}
        .chart {{
            background: #1e1e2e;
            border-radius: 10px;
            padding: 16px;
            margin-bottom: 24px;
        }}
        .summary {{
            background: #1e1e2e;
            border-radius: 10px;
            padding: 24px;
            margin-bottom: 24px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9rem;
        }}
        th {{
            text-align: left;
            padding: 10px 14px;
            border-bottom: 1px solid #313244;
            color: #89b4fa;
            font-weight: 600;
        }}
        td {{
            padding: 10px 14px;
            border-bottom: 1px solid #181825;
            color: #cdd6f4;
        }}
        tr:last-child td {{ border-bottom: none; }}
        tr:hover td {{ background: #181825; }}
    </style>
</head>
<body>
    <h1>GitHub Traffic Dashboard</h1>
    <p class="subtitle">Generated {generated_at} · Data persisted in SQLite</p>
    {summary_table}
    {charts_html}
</body>
</html>"""

    return html


def main():
    if not os.path.exists(DB_PATH):
        print(f"Error: {DB_PATH} not found. Run fetch.py first.")
        return

    print("Loading data from DB...")
    conn = sqlite3.connect(DB_PATH)
    views_data     = load_views(conn)
    clones_data    = load_clones(conn)
    referrers_data = load_referrers(conn)
    conn.close()

    print("Building dashboard...")
    html = build_dashboard(views_data, clones_data, referrers_data)

    with open(OUTPUT_HTML, "w") as f:
        f.write(html)

    print(f"Dashboard written to {OUTPUT_HTML}")
    webbrowser.open(f"file://{os.path.abspath(OUTPUT_HTML)}")


if __name__ == "__main__":
    main()
