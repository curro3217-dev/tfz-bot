import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from pathlib import Path
from typing import List, Optional
from signals import Signal
from levels import HorizontalLevel, DiagonalLevel
from consolidation import Consolidation


SNAPSHOT_DIR = Path(__file__).parent / "snapshots"


def generate_snapshot(
    df: pd.DataFrame,
    signal: Signal,
    h_levels: List[HorizontalLevel] = None,
    d_levels: List[DiagonalLevel] = None,
    consolidations: List[Consolidation] = None,
    candles_before: int = 80,
    candles_after: int = 40,
    save: bool = True,
) -> Optional[str]:
    SNAPSHOT_DIR.mkdir(exist_ok=True)

    start = max(0, signal.trigger_idx - candles_before)
    end = min(len(df), signal.trigger_idx + candles_after)
    chunk = df.iloc[start:end].copy()

    if "timestamp" in chunk.columns:
        x = chunk["timestamp"]
    else:
        x = list(range(start, end))

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.8, 0.2],
        vertical_spacing=0.02,
    )

    # Candlestick
    fig.add_trace(
        go.Candlestick(
            x=x,
            open=chunk["open"],
            high=chunk["high"],
            low=chunk["low"],
            close=chunk["close"],
            name="Price",
            increasing_line_color="#26a69a",
            decreasing_line_color="#ef5350",
        ),
        row=1, col=1,
    )

    # Volume
    colors = ["#26a69a" if c >= o else "#ef5350"
              for c, o in zip(chunk["close"], chunk["open"])]
    fig.add_trace(
        go.Bar(x=x, y=chunk["volume"], marker_color=colors, name="Volume", opacity=0.5),
        row=2, col=1,
    )

    # Horizontal levels
    if h_levels:
        for lev in h_levels:
            color = "#ff9800" if lev.side == "above" else "#2196f3"
            fig.add_hline(
                y=lev.price, line_dash="dash", line_color=color, line_width=1,
                annotation_text=f"L {lev.price:.4g} ({lev.touches}t, s:{lev.score:.0f})",
                annotation_font_size=9,
                row=1, col=1,
            )

    # Diagonal levels
    if d_levels:
        for diag in d_levels:
            y0 = diag.price_at(start)
            y1 = diag.price_at(end)
            x0 = x.iloc[0] if hasattr(x, "iloc") else x[0]
            x1 = x.iloc[-1] if hasattr(x, "iloc") else x[-1]
            fig.add_trace(
                go.Scatter(
                    x=[x0, x1], y=[y0, y1],
                    mode="lines", line=dict(color="#9c27b0", width=1, dash="dot"),
                    name=f"Diag ({diag.touches}t)",
                    showlegend=False,
                ),
                row=1, col=1,
            )

    # Consolidation boxes
    if consolidations:
        for c in consolidations:
            if c.end_idx < start or c.start_idx > end:
                continue
            c_start = max(c.start_idx, start) - start
            c_end = min(c.end_idx, end - 1) - start
            if c_start >= len(x) or c_end >= len(x):
                continue
            x0 = x.iloc[c_start] if hasattr(x, "iloc") else x[c_start]
            x1 = x.iloc[c_end] if hasattr(x, "iloc") else x[c_end]
            fig.add_shape(
                type="rect", x0=x0, x1=x1, y0=c.range_low, y1=c.range_high,
                fillcolor="rgba(33,150,243,0.1)", line=dict(color="#2196f3", width=1),
                row=1, col=1,
            )

    # Entry marker
    entry_x_idx = signal.trigger_idx - start
    if 0 <= entry_x_idx < len(x):
        entry_x = x.iloc[entry_x_idx] if hasattr(x, "iloc") else x[entry_x_idx]
        marker_color = "#4caf50" if signal.direction == "long" else "#f44336"
        marker_symbol = "triangle-up" if signal.direction == "long" else "triangle-down"
        fig.add_trace(
            go.Scatter(
                x=[entry_x], y=[signal.entry_price],
                mode="markers", marker=dict(color=marker_color, size=14, symbol=marker_symbol),
                name=f"Entry {signal.direction}",
            ),
            row=1, col=1,
        )

    # SL and TP lines
    fig.add_hline(
        y=signal.stop_loss, line_dash="dash", line_color="#f44336", line_width=1,
        annotation_text=f"SL {signal.stop_loss:.4g}", annotation_font_size=9,
        row=1, col=1,
    )
    fig.add_hline(
        y=signal.take_profit, line_dash="dash", line_color="#4caf50", line_width=1,
        annotation_text=f"TP {signal.take_profit:.4g}", annotation_font_size=9,
        row=1, col=1,
    )

    # Layout
    title = (
        f"{signal.symbol} {signal.timeframe} | {signal.formation_type} "
        f"{signal.direction.upper()} | Score: {signal.total_score}"
    )
    fig.update_layout(
        title=title,
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        height=700,
        width=1200,
        showlegend=False,
    )

    if save:
        ts_str = str(signal.timestamp).replace(":", "-").replace(" ", "_")[:19]
        symbol_clean = signal.symbol.replace("/", "_")
        filename = f"{ts_str}_{symbol_clean}_{signal.timeframe}_{signal.id}.html"
        filepath = SNAPSHOT_DIR / filename
        fig.write_html(str(filepath))
        return str(filepath)

    fig.show()
    return None
