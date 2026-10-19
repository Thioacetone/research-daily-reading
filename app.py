"""Streamlit reading app, usable locally and on Community Cloud."""
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components
from app_branding import ARTWORK,choose_artwork,brand_preview
from reading_library import load_library
from cloud_bundle import ensure_bundled_files

ROOT=Path(__file__).resolve().parent
ensure_bundled_files(ROOT)
if (not st.session_state.get('reading_artwork')
        or not Path(st.session_state.reading_artwork['path']).is_file()):
    st.session_state.reading_artwork=choose_artwork()
artwork=st.session_state.reading_artwork
image=artwork['path']if artwork else ARTWORK
st.set_page_config(page_title='每日论文精读',page_icon=str(image),layout='wide')
if artwork:
    theme=artwork['theme']
    st.markdown('''<style>
    [data-testid="stAppViewContainer"],[data-testid="stHeader"]{background:BG!important;color:TEXT!important}
    [data-testid="stSidebar"]{background:TINT!important;border-right:1px solid BORDER}
    h1,h2,h3{color:ACCENT!important}
    [data-testid="stCaptionContainer"]{color:MUTED!important}
    .stButton>button{border-color:BORDER!important;color:ACCENT!important;background:PANEL!important}
    .stButton>button[kind="primary"]{background:ACCENT!important;color:white!important}
    [data-baseweb="select"]>div{background:PANEL!important;border-color:BORDER!important;color:TEXT!important}
    </style>'''.replace('BG',theme['background']).replace('TEXT',theme['text']).replace('TINT',theme['tint'])
    .replace('BORDER',theme['border']).replace('ACCENT',theme['accent']).replace('MUTED',theme['muted']).replace('PANEL',theme['panel']),unsafe_allow_html=True)

if not st.session_state.get('reading_started'):
    _,centre,_=st.columns([1,2,1])
    with centre:
        st.image(str(image),width=320)
        st.title('每日论文精读')
        st.caption('化学生物学 · 生物正交 · 药物发现 · CADD/AIDD')
        if st.button('进入阅读',type='primary'):
            st.session_state.reading_started=True
            st.rerun()
    st.stop()

with st.sidebar:
    st.image(str(image),width=120)
    st.title('每日论文精读')
    st.caption('英文一段，中文一段')
    if st.button('返回启动页'):
        st.session_state.reading_started=False
        st.rerun()
    st.button('刷新论文')

reports,unavailable=load_library(ROOT)
if not reports:
    st.info('暂时没有可阅读的论文。发布报告后，点击“刷新论文”即可查看。')
    st.stop()

labels=[entry['day'] for entry in reports]
selected=st.sidebar.selectbox('阅读日期',range(len(reports)),format_func=lambda i:labels[i])
entry=reports[selected]
st.title('每日论文精读')
st.caption('推荐日期：'+labels[selected])
if unavailable:
    st.sidebar.caption('部分历史报告暂不可读，其他日期可以正常阅读。')
document=brand_preview(entry['document'],entry['file'].parent,artwork=artwork,embed_image=True)
st.sidebar.download_button('下载当前阅读页',data=document,file_name='reading-'+entry['day']+'.html',mime='text/html')
components.html(document,height=1100,scrolling=True)
