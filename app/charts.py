import plotly.graph_objects as go

PHASE_ORDER = ["powerplay", "middle", "death"]
AXIS_LABELS = {
    "avg": "Average", "sr": "Strike rate", "consistency": "Consistency", "pp_sr": "Powerplay SR",
    "mid_sr": "Middle SR", "death_sr": "Death SR", "peak_runs_per_inn": "Best season",
    "economy": "Economy", "wkts_per_inn": "Wickets/inn", "pp_econ": "Powerplay econ",
    "death_econ": "Death econ",
}


def _layout(fig, title, height=380):
    fig.update_layout(title=title, height=height, margin=dict(l=40, r=20, t=60, b=40),
                      legend=dict(orientation="h", y=-0.2), hovermode="x unified")
    return fig


def season_chart(seasons, title, bar="runs", line="sr", bar_name="Runs", line_name="Strike rate"):
    """Bars per season with a line on a second axis (seasons = chart['batting']['seasons'])."""
    fig = go.Figure()
    fig.add_bar(x=seasons["x"], y=seasons[bar], name=bar_name, opacity=0.8)
    fig.add_scatter(x=seasons["x"], y=seasons[line], name=line_name, yaxis="y2", mode="lines+markers")
    fig.update_layout(yaxis=dict(title=bar_name),
                      yaxis2=dict(title=line_name, overlaying="y", side="right", showgrid=False),
                      xaxis=dict(type="category"))
    return _layout(fig, title)


def rolling_chart(rolling, key, title, label):
    """Form over the last 10 innings across the whole career (rolling = chart['batting']['rolling'])."""
    fig = go.Figure()
    fig.add_scatter(x=rolling["x"], y=rolling[key], mode="lines", name=label, customdata=rolling["date"],
                    hovertemplate="Innings %{x} (%{customdata})<br>" + label + ": %{y:.1f}<extra></extra>")
    fig.update_layout(xaxis_title="Career innings", yaxis_title=label)
    return _layout(fig, title)


def phase_chart(phases, metric, title, label):
    """Powerplay / middle / death bars for one metric (phases = data['batting'] from get_phase_stats)."""
    xs = [p for p in PHASE_ORDER if p in phases]
    ys = [phases[p][metric] for p in xs]
    fig = go.Figure(go.Bar(x=[p.capitalize() for p in xs], y=ys,
                           text=["-" if v is None else f"{v:.1f}" for v in ys], textposition="outside"))
    fig.update_layout(yaxis_title=label)
    return _layout(fig, title, 340)


def radar_chart(radar, title):
    """Comparison radar; 1.0 on an axis means best in the group (radar = chart['radar'])."""
    axes = [AXIS_LABELS.get(a, a) for a in radar["axes"]]
    fig = go.Figure()
    for name, vals in radar["series"].items():
        vals = [0 if v is None else v for v in vals]
        fig.add_scatterpolar(r=vals + vals[:1], theta=axes + axes[:1], fill="toself", name=name, opacity=0.6)
    fig.update_layout(polar=dict(radialaxis=dict(range=[0, 1], showticklabels=False)))
    return _layout(fig, title, 460)


def bar_chart(x, y, title, label):
    """Horizontal ranking bars; the first item is drawn at the top (chart = leaderboard chart)."""
    fig = go.Figure(go.Bar(x=y[::-1], y=x[::-1], orientation="h",
                           text=[f"{v:,.1f}" if isinstance(v, float) else f"{v:,}" for v in y[::-1]],
                           textposition="outside"))
    fig.update_layout(xaxis_title=label)
    fig.update_layout(hovermode="closest")
    return _layout(fig, title, 400)


TEAM_ABBR = {
    "Chennai Super Kings": "CSK", "Mumbai Indians": "MI", "Royal Challengers Bengaluru": "RCB",
    "Kolkata Knight Riders": "KKR", "Sunrisers Hyderabad": "SRH", "Delhi Capitals": "DC",
    "Punjab Kings": "PBKS", "Rajasthan Royals": "RR", "Gujarat Titans": "GT",
    "Lucknow Super Giants": "LSG", "Deccan Chargers": "DCH", "Pune Warriors": "PWI",
    "Gujarat Lions": "GL", "Kochi Tuskers Kerala": "KTK", "Rising Pune Supergiant": "RPS",
}
PALETTE = ["#4c78a8", "#f58518", "#54a24b", "#b279a2", "#e45756", "#72b7b2", "#eeca3b", "#9d755d"]


def timeline_chart(seasons, teams, value_key, title, label, peak_years=(), slump_years=(), mean=None):
    """One bar per season: green = peak, red = slump, bands = team spans (teams = data['teams'])."""
    years = [str(s["year"]) for s in seasons]
    vals = [s[value_key] for s in seasons]
    colors = ["#2ca02c" if s["year"] in peak_years else "#d62728" if s["year"] in slump_years else "#6fa8dc"
              for s in seasons]
    fig = go.Figure(go.Bar(x=years, y=vals, marker_color=colors,
                           text=["-" if v is None else f"{v:.1f}" for v in vals], textposition="outside",
                           hovertemplate="%{x}: %{y:.2f}<extra></extra>"))
    pos = {s["year"]: i for i, s in enumerate(seasons)}
    for k, t in enumerate(teams):
        inside = [y for y in pos if t["from_year"] <= y <= t["to_year"]]
        if inside:
            fig.add_vrect(x0=pos[min(inside)] - 0.5, x1=pos[max(inside)] + 0.5, fillcolor=PALETTE[k % len(PALETTE)],
                          opacity=0.10, layer="below", line_width=0,
                          annotation_text=TEAM_ABBR.get(t["team"], t["team"]), annotation_position="top left")
    if mean is not None:
        fig.add_hline(y=mean, line_dash="dot", annotation_text="career mean", annotation_position="bottom right")
    fig.update_layout(xaxis=dict(type="category"), yaxis_title=label, showlegend=False, hovermode="closest")
    return _layout(fig, title, 430)


def form_chart(rolling, key, title, label, windows=()):
    """Rolling form line with shaded windows: windows = [{'from','to','label','color'}] (ISO dates)."""
    fig = rolling_chart(rolling, key, title, label)
    dates = rolling["date"]
    for w in windows:
        idx = [i for i, d in enumerate(dates) if w["from"] <= d <= w["to"]]
        if idx:
            fig.add_vrect(x0=rolling["x"][idx[0]], x1=rolling["x"][idx[-1]], fillcolor=w["color"], opacity=0.2,
                          line_width=0, annotation_text=w["label"], annotation_position="top left")
    return fig


def win_curve_chart(curve, title):
    """Chasing team's win chance against the first-innings score (curve = predict_chase()['chart'])."""
    fig = go.Figure()
    fig.add_scatter(x=curve["x"], y=[v * 100 for v in curve["y"]], mode="lines", name="Chasing team win %",
                    hovertemplate="Score %{x}: %{y:.0f}%<extra></extra>")
    fig.add_hline(y=50, line_dash="dot")
    fig.add_vline(x=curve["current"], line_dash="dash", annotation_text="this score")
    fig.update_layout(xaxis_title="First-innings score", yaxis_title="Chasing team win %",
                      yaxis_range=[0, 100], showlegend=False)
    return _layout(fig, title, 360)


def ground_scores_chart(chart, title):
    """Average first-innings score at a ground by season, with its par line (chart = get_match_preview()['chart'])."""
    fig = go.Figure()
    fig.add_scatter(x=[str(x) for x in chart["x"]], y=chart["avg_first"], mode="lines+markers",
                    customdata=chart["matches"],
                    hovertemplate="%{x}: %{y:.0f} runs (%{customdata} matches)<extra></extra>")
    fig.add_hline(y=chart["par"], line_dash="dot", annotation_text="par")
    fig.update_layout(yaxis_title="Average first-innings score", showlegend=False, hovermode="closest")
    return _layout(fig, title, 340)
