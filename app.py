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
from paper_library import DIRECTION_LABELS,TYPE_LABELS,as_collection,build_paper_library,filter_papers,reading_period,beijing_today,page_parameters,selected_paper,published_signature,category_counts
from reading_view import article_cards,hero,navigation_script,page_css,directory_metadata

ROOT=Path(__file__).resolve().parent
ensure_bundled_files(ROOT)
if (not st.session_state.get('reading_artwork')
        or not Path(st.session_state.reading_artwork['path']).is_file()):
    st.session_state.reading_artwork=choose_artwork()
artwork=st.session_state.reading_artwork
image=artwork['path'] if artwork else ARTWORK
st.set_page_config(page_title='每日论文精读',page_icon=str(image),layout='wide',initial_sidebar_state='collapsed')
st.html('<style>'+(ROOT/'assets/streamlit-chrome.css').read_text(encoding='utf-8')+'</style>')


@st.fragment(run_every='60s')
def follow_published_updates():
    current=published_signature(ROOT)
    previous=st.session_state.get('reading_published_signature',current)
    st.session_state.reading_published_signature=current
    if previous!=current and not st.query_params.get('paper'):
        st.rerun()


follow_published_updates()
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

def open_view(view, kind='all', direction='all', browse=None):
    st.query_params.from_dict(page_parameters(view,kind,direction,browse=browse))
    st.session_state.reading_scroll_top=True


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
                      st.query_params.get('direction','all'),paper=st.query_params.get('paper'),
                      browse=st.query_params.get('browse'))
view=route['view']
kind=route.get('kind','all')
direction=route.get('direction','all')
paper=st.query_params.get('paper')
if paper:
    label='返回往期目录' if view=='archive' else '返回今日目录'
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
    if direction!='all' and not any(r['direction']==direction for r in period):
        direction='all'
    filtered=filter_papers(period,kind,direction)
else:
    filtered=period

browse=route.get('browse')
if browse:
    label='研究方向' if browse=='direction' else '论文类型'
    english='SUBJECT INDEX' if browse=='direction' else 'ARTICLE TYPES'
    choices=category_counts(period,browse,kind,direction)
    st.button('返回往期论文',key='category-back',on_click=open_view,args=('archive',kind,direction))
    st.html('<header id="reading-top" class="reader-category-heading">'
            f'<p>{english}</p><h1>{label}</h1>'
            '<span>按篇数从多到少排列 · 点击分类查看论文</span></header>')
    with st.container(key='reader-category-choices'):
        for offset in range(0,len(choices),2):
            columns=st.columns(2,gap='medium')
            for column,row in zip(columns,choices[offset:offset+2]):
                next_kind=row['key'] if browse=='type' else kind
                next_direction=row['key'] if browse=='direction' else direction
                with column:
                    st.button(f'{row["label"]}\n\n**{row["count"]} 篇**　→',
                              key='category-'+browse+'-'+row['key'],use_container_width=True,
                              on_click=open_view,args=('archive',next_kind,next_direction))
    scroll_to_top()
    st.stop()

entry=as_collection(filtered,view,today)
st.html(hero(entry,image))

with st.container(key='reader-navigation'):
    navigation_column,art_column=st.columns([1,1],vertical_alignment='bottom')
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
    with st.container(key='reader-category-navigation'):
        type_column,direction_column=st.columns(2,gap='medium')
        with type_column:
            st.button('论文类型 · '+TYPE_LABELS[kind]+' →',key='choose-paper-type',
                      use_container_width=True,on_click=open_view,args=('archive',kind,direction,'type'))
        with direction_column:
            st.button('研究方向 · '+('全部方向' if direction=='all' else DIRECTION_LABELS[direction])+' →',
                      key='choose-paper-direction',use_container_width=True,
                      on_click=open_view,args=('archive',kind,direction,'direction'))
    st.caption(f'往期共 {len(period)} 篇不重复论文 · 当前显示 {len(filtered)} 篇 · 点击标题进入单篇阅读')
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
st.html('<div class="reader-section-label"><span>论文目录 <small>CONTENTS</small></span><span>'+str(len(filtered)).zfill(2)+' PAPERS</span></div>')
def render_directory_card(index,record):
    item=record['item']
    title=(item.get('bilingual',{}).get('title_zh') or item.get('title_zh')
           or item.get('paper_title') or item['title'])
    key='paper-open-'+hashlib.sha256(record['key'].encode('utf-8')).hexdigest()[:16]
    with st.container(key=key):
        st.button(f'**{index:02d}**　{title} →',key=key+'-button',use_container_width=True,
                  on_click=open_paper,args=(record['key'],view,kind,direction))
        st.html(directory_metadata(item,record['type'],record['direction']))


with st.container(key='reader-directory'):
    for offset in range(0,len(filtered),2):
        columns=st.columns(2,gap='medium')
        for column,index in zip(columns,range(offset,min(offset+2,len(filtered)))):
            with column:
                render_directory_card(index+1,filtered[index])
