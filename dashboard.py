import sqlite3
import webbrowser
import os
from datetime import datetime, timedelta
import plotly.graph_objects as go

DB_PATH = "traffic.db"
OUTPUT_HTML = "dashboard.html"


# ---------- data loading ----------

def load_views(conn):
    cursor = conn.execute("SELECT repo, date, views, uniques FROM views ORDER BY repo, date")
    data = {}
    for repo, date, views, uniques in cursor.fetchall():
        data.setdefault(repo, {"dates": [], "views": [], "uniques": []})
        data[repo]["dates"].append(date)
        data[repo]["views"].append(views)
        data[repo]["uniques"].append(uniques)
    return data


def load_clones(conn):
    cursor = conn.execute("SELECT repo, date, clones, uniques FROM clones ORDER BY repo, date")
    data = {}
    for repo, date, clones, uniques in cursor.fetchall():
        data.setdefault(repo, {"dates": [], "clones": [], "uniques": []})
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
        data.setdefault(repo, {"referrers": [], "counts": [], "uniques": []})
        data[repo]["referrers"].append(referrer)
        data[repo]["counts"].append(total)
        data[repo]["uniques"].append(total_uniques)
    return data


# ---------- palette (Apple semantic colors, dark mode) ----------

BG_PAGE      = "#000000"
BG_CARD      = "#1c1c1e"
BG_SUBTLE    = "#2c2c2e"
BORDER       = "rgba(255,255,255,0.06)"
TEXT_PRIMARY = "#f5f5f7"
TEXT_MUTED   = "#8e8e93"
TEXT_DIM     = "#636366"

BLUE   = "#0a84ff"   # systemBlue
GREEN  = "#30d158"   # systemGreen
ORANGE = "#ff9f0a"   # systemOrange
PINK   = "#ff375f"   # systemPink (for negative trends)
PURPLE = "#bf5af2"   # systemPurple (referrers)


LAYOUT_BASE = dict(
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    font=dict(
        family='-apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif',
        color=TEXT_MUTED,
        size=11,
    ),
    margin=dict(t=12, b=28, l=36, r=12),
    height=200,
    hovermode="x unified",
    hoverlabel=dict(
        bgcolor=BG_SUBTLE,
        bordercolor=BORDER,
        font=dict(color=TEXT_PRIMARY, size=11,
                  family='-apple-system, "SF Pro Text", sans-serif'),
    ),
    showlegend=False,
    xaxis=dict(
        gridcolor=BORDER,
        linecolor="rgba(0,0,0,0)",
        tickfont=dict(size=10, color=TEXT_DIM),
        showgrid=False,
        zeroline=False,
        tickformat="%d %b",
        showline=False,
        ticks="",
    ),
    yaxis=dict(
        gridcolor=BORDER,
        linecolor="rgba(0,0,0,0)",
        tickfont=dict(size=10, color=TEXT_DIM),
        showgrid=True,
        zeroline=False,
        rangemode="tozero",
        showline=False,
        ticks="",
    ),
)


# ---------- helpers ----------

def _safe_sum(xs):
    return sum(xs) if xs else 0


TREND_WINDOW_DAYS = 7  # compare last N days vs the N days before that


def _aggregate_by_date(repos_iter, data, value_key):
    """Sum a metric across repos, keyed by date. Returns {date_str: total}."""
    out = {}
    for repo in repos_iter:
        rd = data.get(repo, {})
        for d, val in zip(rd.get("dates", []), rd.get(value_key, [])):
            key = d[:10]  # normalize to YYYY-MM-DD
            out[key] = out.get(key, 0) + val
    return out


def _period_trend(by_date, window=TREND_WINDOW_DAYS):
    """Compare sum of last `window` days vs the `window` days before that.
    Uses the most recent date in the data as the anchor (not today's clock date),
    since GitHub traffic data typically lags by a day."""
    if not by_date:
        return None, None
    dates_sorted = sorted(by_date.keys())
    try:
        parsed = [datetime.strptime(d, "%Y-%m-%d") for d in dates_sorted]
    except ValueError:
        return None, None

    anchor = parsed[-1]
    recent_start = anchor - timedelta(days=window - 1)
    prior_end    = recent_start - timedelta(days=1)
    prior_start  = prior_end - timedelta(days=window - 1)

    recent = sum(v for d, v in zip(parsed, [by_date[k] for k in dates_sorted])
                 if recent_start <= d <= anchor)
    prior  = sum(v for d, v in zip(parsed, [by_date[k] for k in dates_sorted])
                 if prior_start <= d <= prior_end)

    # need at least some data in both windows to be meaningful
    if prior == 0:
        return None, None
    pct = (recent - prior) / prior * 100
    return pct, ("↑" if pct >= 0 else "↓")


def _format_trend(by_date, window=TREND_WINDOW_DAYS):
    pct, arrow = _period_trend(by_date, window)
    if pct is None:
        return ""
    color = GREEN if pct >= 0 else PINK
    return (
        f'<span class="trend" style="color:{color}" '
        f'title="last {window} days vs prior {window} days">'
        f'{arrow} {abs(pct):.0f}%</span>'
    )


def _peak(dates, values):
    if not values:
        return None
    idx = max(range(len(values)), key=lambda i: values[i])
    if values[idx] == 0:
        return None
    try:
        d = datetime.strptime(dates[idx][:10], "%Y-%m-%d").strftime("%d %b")
    except Exception:
        d = dates[idx]
    return values[idx], d


# ---------- charts ----------

def _area_chart(dates, primary_vals, primary_name, secondary_vals, secondary_name, color):
    """Filled area for primary metric + thin line for secondary (unique)."""
    fig = go.Figure()

    # primary: filled area
    fig.add_trace(go.Scatter(
        x=dates, y=primary_vals,
        name=primary_name,
        mode="lines",
        line=dict(color=color, width=2, shape="spline", smoothing=0.7),
        fill="tozeroy",
        fillcolor=f"rgba({_hex_rgb(color)},0.18)",
        hovertemplate=f"<b>%{{y}}</b> {primary_name}<extra></extra>",
    ))

    # secondary: dashed line, dimmer
    fig.add_trace(go.Scatter(
        x=dates, y=secondary_vals,
        name=secondary_name,
        mode="lines",
        line=dict(color=TEXT_MUTED, width=1.2, dash="dot", shape="spline", smoothing=0.7),
        hovertemplate=f"<b>%{{y}}</b> {secondary_name}<extra></extra>",
    ))

    layout = _clone_layout()
    fig.update_layout(**layout)
    return fig.to_html(
        full_html=False, include_plotlyjs=False,
        config={"displayModeBar": False, "staticPlot": False},
    )


def _hex_rgb(hexcolor):
    h = hexcolor.lstrip("#")
    return f"{int(h[0:2],16)},{int(h[2:4],16)},{int(h[4:6],16)}"


def _clone_layout():
    # shallow copy so each chart can tweak independently
    layout = {k: (dict(v) if isinstance(v, dict) else v) for k, v in LAYOUT_BASE.items()}
    layout["xaxis"] = dict(LAYOUT_BASE["xaxis"])
    layout["yaxis"] = dict(LAYOUT_BASE["yaxis"])
    return layout


def make_views_chart(v):
    if not v["dates"]:
        return '<div class="empty">no view data</div>'
    return _area_chart(
        v["dates"], v["views"], "views",
        v["uniques"], "unique", BLUE,
    )


def make_clones_chart(c):
    if not c["dates"]:
        return '<div class="empty">no clone activity</div>'
    return _area_chart(
        c["dates"], c["clones"], "clones",
        c["uniques"], "unique", ORANGE,
    )


def make_referrers_chart(referrers_data):
    all_refs = {}
    for _, rdata in referrers_data.items():
        for ref, count in zip(rdata["referrers"], rdata["counts"]):
            all_refs[ref] = all_refs.get(ref, 0) + count
    if not all_refs:
        return None
    sorted_refs = sorted(all_refs.items(), key=lambda x: x[1], reverse=True)[:10]
    names  = [r[0] for r in sorted_refs]
    counts = [r[1] for r in sorted_refs]

    fig = go.Figure(go.Bar(
        x=counts, y=names,
        orientation="h",
        marker=dict(
            color=PURPLE,
            opacity=0.85,
            line=dict(width=0),
        ),
        text=[f"{c:,}" for c in counts],
        textposition="outside",
        textfont=dict(color=TEXT_MUTED, size=11),
        hovertemplate="<b>%{y}</b><br>%{x} views<extra></extra>",
        cliponaxis=False,
    ))
    layout = _clone_layout()
    layout["height"] = max(200, len(names) * 30 + 40)
    layout["margin"] = dict(t=12, b=24, l=140, r=48)
    layout["xaxis"]["showgrid"] = True
    layout["xaxis"]["showticklabels"] = False
    layout["yaxis"]["showgrid"] = False
    layout["yaxis"]["autorange"] = "reversed"
    layout["yaxis"]["tickfont"] = dict(size=11, color=TEXT_PRIMARY)
    fig.update_layout(**layout)
    return fig.to_html(
        full_html=False, include_plotlyjs=False,
        config={"displayModeBar": False},
    )


# ---------- dashboard ----------

def build_dashboard(views_data, clones_data, referrers_data):
    # union of repos across all tables
    all_repos = set(views_data) | set(clones_data) | set(referrers_data)

    def _total_activity(r):
        return (
            _safe_sum(views_data.get(r, {}).get("views", []))
            + _safe_sum(clones_data.get(r, {}).get("clones", []))
        )
    repos = sorted(all_repos, key=_total_activity, reverse=True)

    generated_at = datetime.now().strftime("%d %b %Y · %H:%M")

    total_views   = sum(_safe_sum(views_data.get(r, {}).get("views", []))   for r in repos)
    total_uniques = sum(_safe_sum(views_data.get(r, {}).get("uniques", [])) for r in repos)
    total_clones  = sum(_safe_sum(clones_data.get(r, {}).get("clones", [])) for r in repos)
    total_repos   = len(repos)

    # trend indicators: aggregate across repos BY DATE, then compare
    # last TREND_WINDOW_DAYS vs the TREND_WINDOW_DAYS before that
    views_by_date   = _aggregate_by_date(repos, views_data,  "views")
    uniques_by_date = _aggregate_by_date(repos, views_data,  "uniques")
    clones_by_date  = _aggregate_by_date(repos, clones_data, "clones")

    views_trend   = _format_trend(views_by_date)
    clones_trend  = _format_trend(clones_by_date)
    uniques_trend = _format_trend(uniques_by_date)

    # small caption shown under trend pills so the window is self-documenting
    trend_caption = f'<div class="stat-caption">last {TREND_WINDOW_DAYS}d vs prior {TREND_WINDOW_DAYS}d</div>'

    stat_cards = f"""
    <section class="stats-grid">
        <div class="stat-card">
            <div class="stat-label">views</div>
            <div class="stat-row">
                <div class="stat-value">{total_views:,}</div>
                {views_trend}
            </div>
            {trend_caption if views_trend else ''}
        </div>
        <div class="stat-card">
            <div class="stat-label">unique visitors</div>
            <div class="stat-row">
                <div class="stat-value">{total_uniques:,}</div>
                {uniques_trend}
            </div>
            {trend_caption if uniques_trend else ''}
        </div>
        <div class="stat-card">
            <div class="stat-label">clones</div>
            <div class="stat-row">
                <div class="stat-value">{total_clones:,}</div>
                {clones_trend}
            </div>
            {trend_caption if clones_trend else ''}
        </div>
        <div class="stat-card">
            <div class="stat-label">repositories</div>
            <div class="stat-row">
                <div class="stat-value">{total_repos}</div>
            </div>
        </div>
    </section>
    """

    repo_sections_html = ""
    for repo in repos:
        v = views_data.get(repo,  {"dates": [], "views":  [], "uniques": []})
        c = clones_data.get(repo, {"dates": [], "clones": [], "uniques": []})

        repo_views   = _safe_sum(v["views"])
        repo_uniques = _safe_sum(v["uniques"])
        repo_clones  = _safe_sum(c["clones"])

        peak = _peak(v["dates"], v["views"])
        peak_str = f"peak {peak[0]} on {peak[1]}" if peak else ""

        views_chart  = make_views_chart(v)
        clones_chart = make_clones_chart(c)

        repo_sections_html += f"""
        <article class="repo-section">
            <header class="repo-header">
                <div class="repo-title-row">
                    <h3 class="repo-name">{repo}</h3>
                    {f'<span class="repo-peak">{peak_str}</span>' if peak_str else ''}
                </div>
                <div class="repo-meta">
                    <span><strong>{repo_views:,}</strong> views</span>
                    <span class="dot">·</span>
                    <span><strong>{repo_uniques:,}</strong> unique</span>
                    <span class="dot">·</span>
                    <span><strong>{repo_clones:,}</strong> clones</span>
                </div>
            </header>
            <div class="chart-grid">
                <div class="chart-wrap">
                    <div class="chart-label">
                        <span class="dot-blue"></span> views
                        <span class="chart-label-muted">vs unique visitors</span>
                    </div>
                    {views_chart}
                </div>
                <div class="chart-wrap">
                    <div class="chart-label">
                        <span class="dot-orange"></span> clones
                        <span class="chart-label-muted">vs unique cloners</span>
                    </div>
                    {clones_chart}
                </div>
            </div>
        </article>
        """

    ref_chart = make_referrers_chart(referrers_data)
    referrers_html = ""
    if ref_chart:
        referrers_html = f"""
        <article class="repo-section">
            <header class="repo-header">
                <div class="repo-title-row">
                    <h3 class="repo-name">top referrers</h3>
                </div>
                <div class="repo-meta">
                    <span>all repositories combined</span>
                </div>
            </header>
            <div class="chart-wrap chart-wrap-full">{ref_chart}</div>
        </article>
        """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GitHub Traffic</title>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <style>
        :root {{
            --bg-page:     #000000;
            --bg-card:     #1c1c1e;
            --bg-subtle:   #2c2c2e;
            --border:      rgba(255,255,255,0.06);
            --text:        #f5f5f7;
            --text-muted:  #8e8e93;
            --text-dim:    #636366;
            --blue:        #0a84ff;
            --green:       #30d158;
            --orange:      #ff9f0a;
            --purple:      #bf5af2;
            --pink:        #ff375f;
            --radius:      14px;
            --radius-sm:   10px;
        }}

        *, *::before, *::after {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        html, body {{
            background: var(--bg-page);
            color: var(--text);
            font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display",
                         "Helvetica Neue", Helvetica, Arial, sans-serif;
            font-size: 14px;
            line-height: 1.5;
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
            font-feature-settings: "ss01", "tnum";
        }}

        body {{
            max-width: 1040px;
            margin: 0 auto;
            padding: 48px 32px 80px;
        }}

        /* ----- header ----- */
        .header {{
            display: flex;
            align-items: baseline;
            justify-content: space-between;
            margin-bottom: 36px;
            gap: 16px;
        }}

        .header-title {{
            font-size: 28px;
            font-weight: 700;
            letter-spacing: -0.6px;
            color: var(--text);
        }}

        .header-subtitle {{
            font-size: 13px;
            color: var(--text-dim);
            font-variant-numeric: tabular-nums;
        }}

        /* ----- stats grid ----- */
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 12px;
            margin-bottom: 24px;
        }}

        .stat-card {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            padding: 18px 20px;
            transition: transform 0.15s ease, background 0.15s ease;
        }}

        .stat-card:hover {{
            background: #222224;
            transform: translateY(-1px);
        }}

        .stat-label {{
            font-size: 12px;
            color: var(--text-muted);
            font-weight: 500;
            margin-bottom: 8px;
            letter-spacing: -0.1px;
        }}

        .stat-row {{
            display: flex;
            align-items: baseline;
            gap: 10px;
        }}

        .stat-value {{
            font-size: 28px;
            font-weight: 600;
            letter-spacing: -0.8px;
            color: var(--text);
            font-variant-numeric: tabular-nums;
        }}

        .trend {{
            font-size: 12px;
            font-weight: 600;
            padding: 2px 8px;
            border-radius: 6px;
            background: rgba(255,255,255,0.04);
            letter-spacing: -0.1px;
        }}

        .stat-caption {{
            font-size: 11px;
            color: var(--text-dim);
            margin-top: 6px;
            letter-spacing: -0.1px;
        }}

        /* ----- repo section ----- */
        .repo-section {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            padding: 22px 24px 16px;
            margin-bottom: 14px;
        }}

        .repo-header {{
            margin-bottom: 18px;
        }}

        .repo-title-row {{
            display: flex;
            align-items: baseline;
            gap: 14px;
            margin-bottom: 4px;
        }}

        .repo-name {{
            font-size: 17px;
            font-weight: 600;
            color: var(--text);
            letter-spacing: -0.3px;
        }}

        .repo-peak {{
            font-size: 11px;
            color: var(--text-muted);
            background: rgba(10, 132, 255, 0.12);
            color: var(--blue);
            padding: 2px 8px;
            border-radius: 6px;
            font-weight: 500;
            letter-spacing: -0.1px;
        }}

        .repo-meta {{
            font-size: 13px;
            color: var(--text-muted);
            display: flex;
            align-items: center;
            gap: 8px;
            font-variant-numeric: tabular-nums;
        }}

        .repo-meta strong {{
            color: var(--text);
            font-weight: 600;
        }}

        .repo-meta .dot {{
            color: var(--text-dim);
        }}

        /* ----- charts ----- */
        .chart-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
        }}

        .chart-wrap {{
            background: transparent;
            border-radius: var(--radius-sm);
            overflow: hidden;
            position: relative;
        }}

        .chart-wrap-full {{
            margin-top: 8px;
        }}

        .chart-label {{
            font-size: 12px;
            color: var(--text);
            font-weight: 500;
            padding: 8px 4px 4px;
            display: flex;
            align-items: center;
            gap: 8px;
            letter-spacing: -0.1px;
        }}

        .chart-label-muted {{
            color: var(--text-dim);
            font-weight: 400;
        }}

        .dot-blue, .dot-orange {{
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
        }}

        .dot-blue   {{ background: var(--blue);   box-shadow: 0 0 8px rgba(10,132,255,0.4); }}
        .dot-orange {{ background: var(--orange); box-shadow: 0 0 8px rgba(255,159,10,0.4); }}

        .empty {{
            padding: 40px 16px;
            text-align: center;
            color: var(--text-dim);
            font-size: 13px;
            font-style: normal;
            background: rgba(255,255,255,0.015);
            border-radius: var(--radius-sm);
            margin: 8px 4px 4px;
        }}

        /* ----- responsive ----- */
        @media (max-width: 880px) {{
            body {{ padding: 32px 20px 64px; }}
            .stats-grid {{ grid-template-columns: repeat(2, 1fr); }}
            .chart-grid {{ grid-template-columns: 1fr; }}
            .header-title {{ font-size: 24px; }}
        }}

        @media (max-width: 480px) {{
            body {{ padding: 24px 16px 48px; }}
            .repo-section {{ padding: 18px 18px 14px; }}
            .stat-card {{ padding: 14px 16px; }}
            .stat-value {{ font-size: 24px; }}
            .repo-title-row {{ flex-wrap: wrap; gap: 8px; }}
        }}

        /* ----- plotly overrides ----- */
        .js-plotly-plot .plotly .modebar {{ display: none !important; }}
    </style>
</head>
<body>
    <header class="header">
        <h1 class="header-title">GitHub Traffic</h1>
        <span class="header-subtitle">Updated {generated_at}</span>
    </header>

    {stat_cards}

    <main>
        {repo_sections_html}
        {referrers_html}
    </main>
</body>
</html>"""

    return html


def main():
    if not os.path.exists(DB_PATH):
        print(f"Error: {DB_PATH} not found. Run fetch.py first.")
        return

    print("Loading data from DB...")
    conn = sqlite3.connect(DB_PATH)
    try:
        views_data     = load_views(conn)
        clones_data    = load_clones(conn)
        referrers_data = load_referrers(conn)
    finally:
        conn.close()

    print("Building dashboard...")
    html = build_dashboard(views_data, clones_data, referrers_data)

    with open(OUTPUT_HTML, "w") as f:
        f.write(html)

    print(f"Dashboard written to {OUTPUT_HTML}")
    webbrowser.open(f"file://{os.path.abspath(OUTPUT_HTML)}")


if __name__ == "__main__":
    main()