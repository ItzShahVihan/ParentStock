# app.py
"""
داشبورد نظارت بر عملکرد مزرعه مرغ مادر
داشبورد استریم‌لیت برای پایش گله‌های مادر در مقایسه با استانداردهای نژاد راس
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ------------------------------
# تنظیمات صفحه (باید اولین فراخوانی باشد)
# ------------------------------
st.set_page_config(
    page_title="داشبورد مزرعه مرغ مادر",
    page_icon="🐔",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ------------------------------
# CSS سفارشی
# ------------------------------
st.markdown(
    """
    <style>
    .footer {
        text-align: center;
        margin-top: 3rem;
        padding: 1rem;
        color: #666;
        border-top: 1px solid #e0e0e0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ------------------------------
# توابع کمکی
# ------------------------------


@st.cache_data
def load_daily_data(uploaded_file):
    """بارگذاری و پیش‌پردازش داده‌های روزانه گله"""
    if uploaded_file.name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file, sheet_name=0)

    rename_map = {}
    for col in df.columns:
        col_stripped = col.strip()
        if "date" in col_stripped.lower():
            rename_map[col] = "Date"
        elif "flock" in col_stripped.lower() and "id" in col_stripped.lower():
            rename_map[col] = "Flock ID"
        elif "age" in col_stripped.lower() and "day" in col_stripped.lower():
            rename_map[col] = "Age (days)"
        elif "age" in col_stripped.lower() and "week" in col_stripped.lower():
            rename_map[col] = "Age (weeks)"
        elif "hdp" in col_stripped.lower():
            rename_map[col] = "HDP (%)"
        elif "weight" in col_stripped.lower():
            rename_map[col] = "Average Weight (g)"
        elif "feed" in col_stripped.lower():
            rename_map[col] = "Feed Intake (g/hen/day)"
        elif "mortality" in col_stripped.lower():
            rename_map[col] = "Mortality (%)"
        elif "uniformity" in col_stripped.lower():
            rename_map[col] = "Uniformity (%)"
        elif "temp" in col_stripped.lower():
            rename_map[col] = "Temperature"
        elif "humidity" in col_stripped.lower():
            rename_map[col] = "Humidity"

    df.rename(columns=rename_map, inplace=True)

    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    numeric_cols = [
        "Age (days)",
        "Age (weeks)",
        "HDP (%)",
        "Average Weight (g)",
        "Feed Intake (g/hen/day)",
        "Mortality (%)",
        "Uniformity (%)",
        "Temperature",
        "Humidity",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    essential = ["Date", "Flock ID", "Age (weeks)", "HDP (%)", "Average Weight (g)"]
    df.dropna(subset=[c for c in essential if c in df.columns], inplace=True)
    return df


@st.cache_data
def load_target_data(uploaded_file):
    """بارگذاری و پیش‌پردازش جدول استانداردهای هدف"""
    if uploaded_file.name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file, sheet_name=0)

    rename_map = {}
    for col in df.columns:
        col_stripped = col.strip()
        if "age" in col_stripped.lower() and "week" in col_stripped.lower():
            rename_map[col] = "Age (weeks)"
        elif "hdp" in col_stripped.lower():
            rename_map[col] = "Target HDP (%)"
        elif "weight" in col_stripped.lower():
            rename_map[col] = "Target Weight (g)"
        elif "feed" in col_stripped.lower():
            rename_map[col] = "Target Feed Intake (g)"

    df.rename(columns=rename_map, inplace=True)

    for col in [
        "Age (weeks)",
        "Target HDP (%)",
        "Target Weight (g)",
        "Target Feed Intake (g)",
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df.dropna(subset=["Age (weeks)"], inplace=True)
    df["Age (weeks)"] = df["Age (weeks)"].astype(int)
    return df


def merge_with_targets(daily_df, target_df):
    """ترکیب داده‌های روزانه با استانداردهای هدف بر اساس سن هفتگی کامل"""
    if "Age (weeks)" in daily_df.columns:
        daily_df["Age_week_match"] = daily_df["Age (weeks)"].apply(
            lambda x: int(x) if pd.notna(x) else None
        )
    else:
        st.error("داده‌های روزانه باید دارای ستون 'Age (weeks)' باشند.")
        st.stop()

    merged = daily_df.merge(
        target_df,
        left_on="Age_week_match",
        right_on="Age (weeks)",
        how="left",
        suffixes=("", "_target_dup"),
    )

    if "Age (weeks)_target_dup" in merged.columns:
        merged.drop(columns=["Age (weeks)_target_dup"], inplace=True)

    if "HDP (%)" in merged.columns and "Target HDP (%)" in merged.columns:
        merged["HDP_gap"] = merged["HDP (%)"] - merged["Target HDP (%)"]
    if "Average Weight (g)" in merged.columns and "Target Weight (g)" in merged.columns:
        merged["Weight_gap"] = (
            merged["Average Weight (g)"] - merged["Target Weight (g)"]
        )
    return merged


def classify_status(hdp_gap, weight_gap):
    """طبقه‌بندی وضعیت گله بر اساس میزان انحراف."""
    if pd.isna(hdp_gap) or pd.isna(weight_gap):
        return "نامشخص"
    if abs(hdp_gap) > 5 or abs(weight_gap) > 100:
        return "بحرانی"
    elif abs(hdp_gap) > 2 or abs(weight_gap) > 50:
        return "هشدار"
    else:
        return "خوب"


def plot_deviation_fill(actual, target, dates, ylabel, title, actual_name, target_name):
    """نمودار انحراف با ناحیه سایه‌دار و تولتیپ کامل"""
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=actual,
            mode="lines+markers",
            name=actual_name,
            line=dict(color="#1f77b4", width=2),
            marker=dict(size=6),
            hovertemplate="<b>%{fullData.name}</b><br>تاریخ: %{x|%Y-%m-%d}<br>مقدار: %{y:.1f}<extra></extra>",
        )
    )
    if target is not None and target.notna().any():
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=target,
                mode="lines+markers",
                name=target_name,
                line=dict(dash="dash", color="#ff7f0e", width=2),
                marker=dict(size=6),
                fill="tonexty",
                fillcolor="rgba(255, 127, 14, 0.15)",
                hovertemplate="<b>%{fullData.name}</b><br>تاریخ: %{x|%Y-%m-%d}<br>مقدار: %{y:.1f}<extra></extra>",
            )
        )
    fig.update_layout(
        title=title,
        xaxis_title="تاریخ",
        yaxis_title=ylabel,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=40, t=60, b=40),
    )
    return fig


# ------------------------------
# برنامه اصلی
# ------------------------------
def main():
    # ---------- ورود با رمز عبور ----------
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        with st.sidebar:
            st.header("🔒 ورود به داشبورد")
            pwd = st.text_input("رمز عبور", type="password")
            if st.button("ورود"):
                if pwd == "Farm2025!":  # رمز دلخواه خود را اینجا بگذارید
                    st.session_state.authenticated = True
                    st.rerun()
                else:
                    st.error("رمز عبور اشتباه است")
        st.stop()  # تا زمانی که وارد نشده، بقیه برنامه اجرا نشود

    # ---------- بعد از ورود ----------
    st.title("🐓 داشبورد عملکرد مزرعه مرغ مادر 🌾")
    st.markdown(
        "نظارت بر عملکرد گله‌های مادر در مقایسه با استانداردهای نژاد **راس**. "
        "لطفاً داده‌های روزانه و منحنی‌های هدف خود را بارگذاری کنید."
    )

    with st.sidebar:
        st.header("📂 بارگذاری داده")
        daily_file = st.file_uploader(
            "داده‌های روزانه گله (CSV یا Excel)",
            type=["csv", "xlsx", "xls"],
            key="daily",
        )
        target_file = st.file_uploader(
            "داده‌های استاندارد هدف (CSV یا Excel)",
            type=["csv", "xlsx", "xls"],
            key="target",
        )

        if not daily_file or not target_file:
            st.info("👆 لطفاً هر دو فایل را بارگذاری کنید تا داشبورد فعال شود.")
            st.stop()

        daily_df = load_daily_data(daily_file)
        target_df = load_target_data(target_file)
        merged_df = merge_with_targets(daily_df, target_df)

        st.header("🔎 فیلترها")
        flock_list = sorted(merged_df["Flock ID"].dropna().unique())
        selected_flock = st.selectbox("شناسه گله", flock_list)

        min_date = merged_df["Date"].min().date()
        max_date = merged_df["Date"].max().date()
        date_range = st.date_input(
            "محدوده تاریخ",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
        )

        st.markdown("---")
        st.markdown(
            "<div style='text-align: center; color: #888;'>ساخته‌شده توسط <b>ویهان شاهینی</b></div>",
            unsafe_allow_html=True,
        )

    if len(date_range) == 2:
        start_date, end_date = date_range
        mask = (
            (merged_df["Flock ID"] == selected_flock)
            & (merged_df["Date"] >= pd.to_datetime(start_date))
            & (merged_df["Date"] <= pd.to_datetime(end_date))
        )
        flock_data = merged_df.loc[mask].sort_values("Date")
    else:
        st.warning("لطفاً یک بازه تاریخ کامل انتخاب کنید.")
        st.stop()

    if flock_data.empty:
        st.warning("داده‌ای برای گله و بازه تاریخ انتخاب شده وجود ندارد.")
        st.stop()

    # KPI cards
    latest_row = flock_data.iloc[-1]
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🥚 درصد تولید (HDP)", f"{latest_row['HDP (%)']:.1f} %")
    col2.metric("⚖️ میانگین وزن (گرم)", f"{latest_row['Average Weight (g)']:.0f} g")
    col3.metric(
        "🌽 مصرف خوراک (گرم/روز)", f"{latest_row['Feed Intake (g/hen/day)']:.1f}"
    )
    col4.metric("💀 تلفات (%)", f"{latest_row['Mortality (%)']:.2f} %")

    st.markdown("---")

    # HDP Analysis
    st.header("📈 تحلیل تولید (HDP)")
    fig_hdp = plot_deviation_fill(
        actual=flock_data["HDP (%)"],
        target=flock_data.get("Target HDP (%)"),
        dates=flock_data["Date"],
        ylabel="HDP (%)",
        title="تولید (HDP): واقعی در مقابل هدف",
        actual_name="تولید واقعی",
        target_name="تولید هدف",
    )
    st.plotly_chart(fig_hdp, use_container_width=True)

    # Weight Analysis
    st.header("⚖️ تحلیل وزن")
    fig_weight = plot_deviation_fill(
        actual=flock_data["Average Weight (g)"],
        target=flock_data.get("Target Weight (g)"),
        dates=flock_data["Date"],
        ylabel="وزن (گرم)",
        title="میانگین وزن: واقعی در مقابل هدف",
        actual_name="وزن واقعی",
        target_name="وزن هدف",
    )
    st.plotly_chart(fig_weight, use_container_width=True)

    # Feed Intake Trend
    st.header("🍽️ روند مصرف خوراک")
    fig_feed = px.line(
        flock_data,
        x="Date",
        y="Feed Intake (g/hen/day)",
        markers=True,
        title="مصرف خوراک روزانه به ازای هر مرغ",
        labels={"Feed Intake (g/hen/day)": "گرم/مرغ/روز", "Date": "تاریخ"},
    )
    fig_feed.update_traces(
        hovertemplate="<b>تاریخ: %{x|%Y-%m-%d}</b><br>مصرف: %{y:.1f} g<extra></extra>"
    )
    st.plotly_chart(fig_feed, use_container_width=True)

    # Mortality Trend
    st.header("⚠️ روند تلفات")
    fig_mort = px.line(
        flock_data,
        x="Date",
        y="Mortality (%)",
        markers=True,
        title="نرخ تلفات روزانه",
        labels={"Mortality (%)": "تلفات (%)", "Date": "تاریخ"},
    )
    fig_mort.update_traces(
        hovertemplate="<b>تاریخ: %{x|%Y-%m-%d}</b><br>تلفات: %{y:.2f}%<extra></extra>"
    )
    st.plotly_chart(fig_mort, use_container_width=True)

    # Performance Insights
    st.header("📊 بینش عملکرد")
    hdp_gap = latest_row.get("HDP_gap", None)
    weight_gap = latest_row.get("Weight_gap", None)

    col_a, col_b, col_c = st.columns(3)
    if pd.notna(hdp_gap):
        col_a.metric("انحراف تولید (HDP)", f"{hdp_gap:+.1f} %")
    else:
        col_a.metric("انحراف تولید (HDP)", "ناموجود")
    if pd.notna(weight_gap):
        col_b.metric("انحراف وزن", f"{weight_gap:+.0f} g")
    else:
        col_b.metric("انحراف وزن", "ناموجود")

    status = classify_status(hdp_gap, weight_gap)
    if status == "خوب":
        col_c.success(f"🐣 وضعیت گله: **{status}**")
    elif status == "هشدار":
        col_c.warning(f"⚠️ وضعیت گله: **{status}**")
    elif status == "بحرانی":
        col_c.error(f"🚨 وضعیت گله: **{status}**")
    else:
        col_c.info("وضعیت: داده ناکافی")

    # Expanded deviation table
    with st.expander("📋 داده‌های انحراف جزئی (۷ روز اخیر)"):
        detail_df = flock_data.tail(7)[
            [
                "Date",
                "HDP (%)",
                "Target HDP (%)",
                "HDP_gap",
                "Average Weight (g)",
                "Target Weight (g)",
                "Weight_gap",
            ]
        ].copy()
        detail_df.rename(
            columns={
                "Date": "تاریخ",
                "HDP (%)": "HDP واقعی",
                "Target HDP (%)": "HDP هدف",
                "HDP_gap": "شکاف HDP",
                "Average Weight (g)": "وزن واقعی",
                "Target Weight (g)": "وزن هدف",
                "Weight_gap": "شکاف وزن",
            },
            inplace=True,
        )
        st.dataframe(detail_df.style.format(precision=1), use_container_width=True)

    # Footer
    st.markdown(
        "<div class='footer'>🐓 ساخته‌شده با دقت توسط <b>ویهان شاهینی</b> | نرم‌افزار مدیریت مزرعه 🌾</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
