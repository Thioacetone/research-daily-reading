"""A continuous Streamlit reading room for local and cloud-published reports."""
from pathlib import Path
import streamlit as st
from app_branding import ARTWORK,choose_artwork,palette_from_rgb,brand_preview
from cloud_bundle import ensure_bundled_files
from reading_library import load_library
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

days=[entry['day'] for entry in reports]
if st.session_state.get('reading_issue',days[0]) not in days:
    st.session_state.reading_issue=days[0]
entry=next(report for report in reports if report['day']==st.session_state.get('reading_issue',days[0]))
try:
    articles=article_cards(entry)
except ValueError:
    st.warning('这份历史报告暂时无法使用新版排版，可以保存历史原文后阅读。')
    document=brand_preview(entry['document'],entry['file'].parent,artwork=artwork,embed_image=True)
    st.download_button('保存历史原文',data=document,file_name='reading-original-'+entry['day']+'.html',mime='text/html')
    st.stop()
st.html(hero(entry,image))

date_column,art_column,download_column=st.columns([2.2,1,1],vertical_alignment='bottom')
with date_column:
    st.selectbox('阅读日期',days,key='reading_issue',format_func=lambda day:day.replace('-',' / '))
with art_column:
    if st.button('换一张配图',use_container_width=True):
        st.session_state.reading_artwork=choose_artwork()
        st.rerun()
with download_column:
    st.download_button('保存阅读页',data=standalone(entry,image,css),file_name='reading-'+entry['day']+'.html',
                       mime='text/html',use_container_width=True)

if unavailable:
    st.caption('部分历史报告暂不可读，其他日期可以正常阅读。')
st.html(table_of_contents(entry))
for article in articles:
    st.html(article)
st.html('<footer class="reader-footer">每日论文精读 · 英文原文与中文对照<br>化学生物学 / 药物发现 / CADD · AIDD / 生物正交</footer>')
st.html('<script>'+navigation_script(ROOT)+'</script>',unsafe_allow_javascript=True)
