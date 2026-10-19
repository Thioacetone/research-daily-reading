"""A classified, deduplicated Streamlit library of published deep readings."""
from pathlib import Path
import importlib
import json
import hashlib
import streamlit as st

importlib.invalidate_caches()
from app_branding import ARTWORK,choose_artwork,palette_from_rgb
from cloud_bundle import ensure_bundled_files
from reading_library import load_library
from paper_library import DIRECTION_LABELS,TYPE_LABELS,as_collection,build_paper_library,filter_papers,reading_period,beijing_today,page_parameters,selected_paper
from reading_view import article_cards,hero,navigation_script,page_css,table_of_contents

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
    history_path=ROOT/'site-publication.json'
    history=json.loads(history_path.read_text(encoding='utf-8')) if history_path.is_file() else {}
    records=build_paper_library(reports,history)
except (ValueError,OSError):
    st.error('论文库暂时无法完整读取，请稍后刷新。')
    st.stop()

def open_view(view, kind='all', direction='all'):
    st.query_params.from_dict(page_parameters(view,kind,direction))
    st.session_state.reading_scroll_top=True


def apply_filters():
    open_view('archive',st.session_state.paper_type_filter,st.session_state.paper_direction_filter)


def open_paper(key, view, kind, direction):
    st.query_params.from_dict(page_parameters(view,kind,direction,key))
    st.session_state.reading_scroll_top=True


def scroll_to_top():
    script=navigation_script(ROOT)
    if st.session_state.pop('reading_scroll_top',False):
        script+="\ndocument.getElementById('reading-top')?.scrollIntoView({block:'start',behavior:'instant'});"
    st.html('<script>'+script+'</script>',unsafe_allow_javascript=True)


today=beijing_today()
route=page_parameters(st.query_params.get('view','today'),st.query_params.get('kind','all'),
                      st.query_params.get('direction','all'))
view=route['view']
kind=route.get('kind','all')
direction=route.get('direction','all')
paper=st.query_params.get('paper')
if paper:
    label='返回往期目录' if view=='archive' else '返回今日论文'
    st.html('<div id="reading-top"><p class="reader-eyebrow">PAPER READING / 单篇精读</p></div>')
    st.button(label,key='paper-back-top',on_click=open_view,args=(view,kind,direction))
    selected=selected_paper(records,paper,view,today)
    if selected is None:
        st.info('这篇论文暂不可用，请返回目录选择其他论文。')
    else:
        detail=as_collection([selected],'paper',today)
        for article in article_cards(detail):
            st.html(article)
        st.button(label,key='paper-back-bottom',on_click=open_view,args=(view,kind,direction))
    scroll_to_top()
    st.stop()

period=reading_period(records,view,today)
if view=='archive':
    type_options=['all','review','research']
    direction_options=['all']+[key for key in DIRECTION_LABELS if any(r['direction']==key for r in period)]
    if direction not in direction_options:
        direction='all'
    st.session_state.paper_type_filter=kind
    st.session_state.paper_direction_filter=direction
    filtered=filter_papers(period,kind,direction)
else:
    filtered=period
entry=as_collection(filtered,view,today)
st.html(hero(entry,image))

navigation_column,art_column=st.columns([3,1],vertical_alignment='bottom')
with navigation_column:
    if view=='today':
        st.button('查看往期论文',on_click=open_view,args=('archive',),use_container_width=True)
    else:
        st.button('返回今日论文',on_click=open_view,args=('today',),use_container_width=True)
with art_column:
    if st.button('换一张配图',use_container_width=True):
        st.session_state.reading_artwork=choose_artwork()
        st.rerun()

if view=='archive':
    type_column,direction_column=st.columns([1,2],vertical_alignment='bottom')
    with type_column:
        st.selectbox('论文类型',type_options,key='paper_type_filter',filter_mode=None,accept_new_options=False,
                     on_change=apply_filters,
                     format_func=lambda key:TYPE_LABELS[key]+f" · {len(filter_papers(period,key))} 篇")
    with direction_column:
        st.selectbox('研究方向',direction_options,key='paper_direction_filter',filter_mode=None,accept_new_options=False,
                     on_change=apply_filters,
                     format_func=lambda key:('全部方向' if key=='all' else DIRECTION_LABELS[key])+f" · {len(filter_papers(period,kind,key))} 篇")
    st.caption(f'往期共 {len(period)} 篇不重复论文 · 当前显示 {len(filtered)} 篇 · 点击标题进入单篇阅读')
else:
    st.caption(f'{today} · 今日精读 {len(filtered)} 篇')
scroll_to_top()
if unavailable:
    st.caption('部分历史报告暂不可读，其他论文可以正常阅读。')
if not filtered:
    if view=='today':
        st.info('今天的精读论文尚未更新，可以点击“查看往期论文”继续阅读。')
    elif not period:
        st.info('暂时没有往期论文，之后的历史推荐会在这里显示。')
    else:
        st.info('暂时没有同时符合这两个分类的论文，可以选择“全部方向”或“全部类型”查看其他内容。')
    st.stop()
if view=='archive':
    st.html('<div class="reader-section-label"><span>论文目录</span><span>'+str(len(filtered))+' PAPERS</span></div>')
    for index,record in enumerate(filtered,1):
        item=record['item']
        title=(item.get('bilingual',{}).get('title_zh') or item.get('title_zh')
               or item.get('paper_title') or item['title'])
        key='paper-open-'+hashlib.sha256(record['key'].encode('utf-8')).hexdigest()[:16]
        with st.container(key=key):
            st.button(f'{index:02d}　{title} →',key=key+'-button',use_container_width=True,
                      on_click=open_paper,args=(record['key'],view,kind,direction))
            st.caption(item.get('venue','')+' · '+TYPE_LABELS.get(record['type'],'类型待核实')
                       +' · '+DIRECTION_LABELS[record['direction']])
else:
    st.html(table_of_contents(entry))
    for article in article_cards(entry):
        st.html(article)
st.html('<footer class="reader-footer">每日论文精读 · '+('往期论文' if view=='archive' else '今日精读')+'<br>英文原文与中文对照 · 相同 DOI 合并展示</footer>')
