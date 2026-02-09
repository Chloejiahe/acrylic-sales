import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
# 不需要再 import requests 和 BytesIO 了

# -----------------------------------------------------------------------------
# 1. 页面配置与 本地数据读取
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Ohuhu 丙烯笔大盘与VOM稳定性看板", layout="wide", page_icon="🎨")

# 直接指定文件名即可，因为它就在你的 GitHub 仓库根目录
EXCEL_FILE = "丙烯笔打标总表.xlsx"

@st.cache_data(ttl=3600)
def load_data_local(file_path):
    try:
        # 直接使用 pandas 读取本地文件
        df = pd.read_excel(file_path)
        
        # 日期预处理
        df['Date_Obj'] = pd.to_datetime(df['Date'], format='%Y%m')
        df['Date_Str'] = df['Date_Obj'].dt.to_period('M').astype(str)
        df['Quarter'] = df['Date_Obj'].dt.to_period('Q').astype(str)
        df['Year'] = df['Date_Obj'].dt.year
        
        # 数值清洗
        numeric_cols = ['Amount', 'Sales', 'Price', 'Rate', '产品支数']
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        # 计算核心指标
        df['ASP'] = df['Amount'] / df['Sales']
        df['Unit_Price'] = df['Price'] / df['产品支数']
        
        # 【核心：ASIN 稳定性计算】
        total_months_in_dataset = df['Date'].nunique()
        asin_counts = df.groupby('ASIN')['Date'].count().reset_index()
        asin_counts.columns = ['ASIN', '在榜月数']
        
        # 合并回主表
        df = df.merge(asin_counts, on='ASIN', how='left')
        df['稳定性评分'] = df['在榜月数'] / total_months_in_dataset
        
        return df, total_months_in_dataset
    except FileNotFoundError:
        st.error(f"找不到文件：{file_path}。请确保该文件已上传到 GitHub 仓库根目录。")
        return pd.DataFrame(), 0
    except Exception as e:
        st.error(f"数据处理出错: {e}")
        return pd.DataFrame(), 0

# 执行读取
df, total_periods = load_data_local(EXCEL_FILE)

if df.empty:
    st.warning("数据表为空，请检查 Excel 文件内容。")
    st.stop()
# -----------------------------------------------------------------------------
# 2. 侧边栏：品牌全量筛选
# -----------------------------------------------------------------------------
st.sidebar.title("🎨 Ohuhu 市场看板")
st.sidebar.info(f"数据周期共计: {total_periods} 个月")

all_brands = sorted(df['Brand'].unique().tolist())
selected_brands = st.sidebar.multiselect("筛选观察品牌 (默认全量)", options=all_brands, default=all_brands)
df_filtered = df[df['Brand'].isin(selected_brands)]

# -----------------------------------------------------------------------------
# 3. 核心板块展示
# -----------------------------------------------------------------------------
tab1, tab2, tab3, tab4 = st.tabs(["📈 大盘规模 Overview", "🏆 品牌份额与ASIN稳定性", "💰 价格段分布", "🔍 VOM 特征穿透"])

# --- TAB 1: 大盘规模 ---
with tab1:
    st.header("1. US 丙烯笔市场规模演变")
    
    # 品牌销售额堆叠面积图
    monthly_sales = df_filtered.groupby(['Date_Str', 'Brand'])['Amount'].sum().reset_index()
    fig_area = px.area(monthly_sales, x='Date_Str', y='Amount', color='Brand', 
                       title="全品牌月度销售额趋势 (堆叠总量)")
    st.plotly_chart(fig_area, use_container_width=True)

    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("年度产品类型分布 (按出墨方式)")
        year_ink = df_filtered.groupby(['Year', '出墨方式'])['Amount'].sum().reset_index()
        st.plotly_chart(px.bar(year_ink, x='Year', y='Amount', color='出墨方式', barmode='group'), use_container_width=True)
    with col_b:
        st.subheader("品牌关键指标月度演变")
        m_choice = st.selectbox("选择指标", ["Price", "Rate", "Sales"], key="metric_s")
        avg_metrics = df_filtered.groupby(['Date_Str', 'Brand'])[m_choice].mean().reset_index()
        st.plotly_chart(px.line(avg_metrics, x='Date_Str', y=m_choice, color='Brand'), use_container_width=True)

# --- TAB 2: 品牌份额与稳定性 (深度解决掉榜问题) ---
with tab2:
    st.header("2. 品牌份额与 ASIN 稳定性洞察")
    
    # 同比/环比/份额表格
    st.subheader("品牌市场表现数据矩阵")
    sub_tab1, sub_tab2, sub_tab3 = st.tabs(["季度同比 YoY", "季度份额 %", "年度份额 %"])
    q_data = df.groupby(['Quarter', 'Brand'])['Amount'].sum().unstack(fill_value=0)
    
    with sub_tab1: st.dataframe(q_data.pct_change(4).style.format("{:.1%}", na_rep='-'))
    with sub_tab2: st.dataframe(q_data.div(q_data.sum(axis=1), axis=0).style.format("{:.1%}", na_rep='-'))
    with sub_tab3: 
        y_data = df.groupby(['Year', 'Brand'])['Amount'].sum().unstack(fill_value=0)
        st.dataframe(y_data.div(y_data.sum(axis=1), axis=0).style.format("{:.1%}", na_rep='-'))

    st.markdown("---")
    
    # ASIN 稳定性与物理特征关联
    st.subheader("🔥 ASIN 在榜月数 vs 产品物理特征分析")
    st.markdown("> 如果一个 ASIN 的在榜月数远小于数据集总月数，说明其竞争稳定性较弱，容易掉出 Top 100。")

    # 聚合 ASIN 明细（不仅看ASIN，看特征）
    asin_attr = df_filtered.groupby(['ASIN', 'Brand', '是否双头', '出墨方式', '产品支数', '笔头类型']).agg({
        '在榜月数': 'max',
        'Amount': 'sum',
        'Price': 'mean',
        'Rate': 'mean'
    }).reset_index()

    # 稳定性散点图
    fig_stable = px.scatter(asin_attr, x='在榜月数', y='Amount', 
                            size='Price', color='出墨方式', 
                            symbol='是否双头',
                            hover_data=['ASIN', '产品支数', '笔头类型'],
                            labels={'Amount': '累计总销售额', 'Price': '平均客单价'},
                            title="ASIN 稳定性坐标图 (右侧为常青树，左侧为掉榜/闪现产品)")
    st.plotly_chart(fig_stable, use_container_width=True)

    # 掉榜风险清单
    col_x, col_y = st.columns(2)
    with col_x:
        st.write("🌲 **市场常青树 (Top 20 稳定 ASIN)**")
        st.dataframe(asin_attr.sort_values(by=['在榜月数', 'Amount'], ascending=False).head(20))
    with col_y:
        st.write("⚠️ **闪现/掉榜预警 (在榜时间短且销售额波动大)**")
        st.dataframe(asin_attr.sort_values(by='在榜月数', ascending=True).head(20))

# --- TAB 3: 价格段分析 ---
with tab3:
    st.header("3. 价格段份额演变")
    price_q = df.groupby(['Quarter', '价格档位'])['Amount'].sum().reset_index()
    st.plotly_chart(px.bar(price_q, x='Quarter', y='Amount', color='价格档位', barmode='stack'), use_container_width=True)
    
    price_tbl = df.pivot_table(index='价格档位', columns='Year', values='Amount', aggfunc='sum').fillna(0)
    st.table(price_tbl.style.format("${:,.0f}"))

# --- TAB 4: VOM 深度穿透 (五大板块) ---
with tab4:
    st.header("4. 丙烯笔 VOM 核心特征分析")
    v1, v2 = st.columns(2)
    with v1:
        st.subheader("1. 包装方式与支数份额 (Sunburst)")
        st.plotly_chart(px.sunburst(df_filtered, path=['包装方式', '产品支数'], values='Amount'), use_container_width=True)
    with v2:
        st.subheader("2. 出墨方式与价位段箱线图")
        st.plotly_chart(px.box(df_filtered, x='出墨方式', y='Price', color='出墨方式', points="all"), use_container_width=True)
    
    v3, v4 = st.columns(2)
    with v3:
        st.subheader("3. 笔头类型与线宽分布")
        st.plotly_chart(px.treemap(df_filtered, path=['笔头类型', '线宽'], values='Amount'), use_container_width=True)
    with v4:
        st.subheader("4. 各品牌单支笔均价 (Unit Price)")
        st.plotly_chart(px.violin(df_filtered, x='Brand', y='Unit_Price', box=True, points="all"), use_container_width=True)
    
    st.subheader("5. 独立色系 vs 混色套装趋势对比")
    df['Color_Type'] = df['Ink_Color'].apply(lambda x: 'Independent' if any(c in str(x) for c in ['White','Black','Gold','Silver','Metallic']) else 'Assorted')
    c_trend = df.groupby(['Date_Str', 'Color_Type'])['Amount'].sum().reset_index()
    st.plotly_chart(px.line(c_trend, x='Date_Str', y='Amount', color='Color_Type', markers=True), use_container_width=True)
