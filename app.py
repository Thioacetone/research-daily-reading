"""A classified, deduplicated Streamlit library of published deep readings."""
from pathlib import Path
import importlib
import streamlit as st

importlib.invalidate_caches()
from app_branding import ARTWORK,choose_artwork,palette_from_rgb
from cloud_bundle import ensure_bundled_files
from reading_library import load_library
from paper_library import DIRECTION_LABELS,TYPE_LABELS,as_collection,build_paper_library,filter_papers
from reading_view import article_cards,hero,navigation_script,page_css,standalone,table_of_contents

ROOT=Path(__file__).resolve().parent
ensure_bundled_files(ROOT)
if (not st.session_state.get('reading_artwork')
        or not Path(st.session_state.reading_artwork['path']).is_file()):
    st.session_state.reading_artwork=choose_artwork()
artwork=st.session_state.reading_artwork
image=artwork['path'] if artwork else ARTWORK
st.set_page_config(page_title='每日论文精读',page_icon=str(image),layout='wide',initial_sidebar_state='collapsed')
theme=artwork['theme'] if artwork else palette_from_rgb((126,145,156))
css=page_css(ROOT,theme)
st.html('<style>'+css+'</style>')

reports,unavailable=load_library(ROOT)
if not reports:
    st.info('暂时没有可阅读的论文。报告发布后，刷新页面即可查看。')
    st.stop()
try:
    records=build_paper_library(reports)
except ValueError:
    st.error('论文库暂时无法完整读取，请稍后刷新。')
    st.stop()

type_options=['all','review','research']
direction_options=['all']+[key for key in DIRECTION_LABELS if any(r['direction']==key for r in records)]
if st.session_state.get('paper_type_filter','all') not in type_options:
    st.session_state.paper_type_filter='all'
if st.session_state.get('paper_direction_filter','all') not in direction_options:
    st.session_state.paper_direction_filter='all'
kind=st.session_state.get('paper_type_filter','all')
direction=st.session_state.get('paper_direction_filter','all')
filtered=filter_papers(records,kind,direction)
entry=as_collection(filtered)
st.html(hero(entry,image))

type_column,direction_column,art_column,download_column=st.columns([1.1,1.8,1,1],vertical_alignment='bottom')
with type_column:
    st.selectbox('论文类型',type_options,key='paper_type_filter',
                 format_func=lambda key:TYPE_LABELS[key]+f" · {len(filter_papers(records,key))} 篇")
with direction_column:
    st.selectbox('研究方向',direction_options,key='paper_direction_filter',
                 format_func=lambda key:('全部方向' if key=='all' else DIRECTION_LABELS[key])+f" · {len(filter_papers(records,kind,key))} 篇")
with art_column:
    if st.button('换一张配图',use_container_width=True):
        st.session_state.reading_artwork=choose_artwork()
        st.rerun()
with download_column:
    st.download_button('保存阅读页',data=standalone(entry,image,css),file_name='reading-library.html',
                       mime='text/html',disabled=not filtered,use_container_width=True)

st.caption(f"论文库共 {len(records)} 篇不重复论文 · 综述 {len(filter_papers(records,'review'))} 篇 · 非综述 {len(filter_papers(records,'research'))} 篇 · 当前显示 {len(filtered)} 篇")
if unavailable:
    st.caption('部分历史报告暂不可读，其他论文可以正常阅读。')
if not filtered:
    st.info('暂时没有同时符合这两个分类的论文，可以选择“全部方向”或“全部类型”查看其他内容。')
    st.stop()
st.html(table_of_contents(entry))
for article in article_cards(entry):
    st.html(article)
st.html('<footer class="reader-footer">每日论文精读 · 按论文类型与研究方向浏览<br>英文原文与中文对照 · 相同 DOI 合并展示</footer>')
st.html('<script>'+navigation_script(ROOT)+'</script>',unsafe_allow_javascript=True)
