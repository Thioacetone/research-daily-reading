"""Present saved scientific copy as a continuous reading page."""
import base64
from datetime import date
import html
import mimetypes
from pathlib import Path
import re
from urllib.parse import urlencode
from paper_library import DIRECTION_LABELS,TYPE_LABELS,paper_direction,paper_type,paper_key,saved_cards,page_parameters


def image_data(path):
    path=Path(path)
    mime=mimetypes.guess_type(path.name)[0] or 'image/jpeg'
    return 'data:'+mime+';base64,'+base64.b64encode(path.read_bytes()).decode('ascii')


def issue_items(entry):
    return [item for section in entry['report']['sections'].values() for item in section['items']]


def hero(entry,image):
    if entry.get('view')=='today':
        eyebrow=f'TODAY’S READING <span> / </span> {entry["today"]} · {entry["count"]:02d} PAPERS'
    elif entry.get('view')=='archive':
        eyebrow=f'READING ARCHIVE <span> / </span> {entry["count"]:02d} PAPERS'
    elif entry.get('collection'):
        eyebrow=f'PAPER LIBRARY <span> / </span> {entry["count"]:02d} PAPERS'
    else:
        day=date.fromisoformat(entry['day'])
        weekday=('周一','周二','周三','周四','周五','周六','周日')[day.weekday()]
        eyebrow=f'DAILY READING <span> / </span> {day:%Y.%m.%d} · {weekday}'
    heading='往期论文' if entry.get('view')=='archive' else '每日论文精读'
    intro='按论文类型与研究方向，找到值得重读的研究。' if entry.get('view')=='archive' else '把值得读的论文，读得更深一点。'
    return (f'<header class="reader-hero" id="reading-top"><div class="reader-hero-copy">'
            f'<p class="reader-eyebrow">{eyebrow}</p>'
            f'<h1>{heading}<span class="reader-heading-dot">.</span></h1>'
            f'<p class="reader-intro">{intro}</p>'
            '<div class="reader-topics"><span>化学生物学</span><span>药物发现</span>'
            '<span>CADD / AIDD</span><span>生物正交</span></div>'
            '</div><figure class="reader-hero-art">'
            f'<img src="{image_data(image)}" alt="本次阅读配图"></figure></header>')


def table_of_contents(entry):
    cards=[]
    for index,item in enumerate(issue_items(entry),1):
        value=item.get('bilingual',{})
        title=value.get('title_zh') or item.get('title_zh') or item.get('paper_title') or item['title']
        updates=entry.get('paper_updates',[])
        badge=('<span class="reader-today">今日更新</span>'
               if index<=len(updates) and updates[index-1]==entry.get('today') else '')
        if entry.get('page_links'):
            href='?'+urlencode(page_parameters(entry.get('view','archive'),entry.get('kind','all'),
                                                entry.get('direction','all'),paper_key(item)))
            target='_self'
        else:
            href=f'#reading-paper-{index}'
            target='_self'
        cards.append(f'<a class="reader-toc-item" href="{html.escape(href,quote=True)}" target="{target}">'
                     f'<span class="reader-toc-number">{index:02d}</span><span class="reader-toc-copy">'
                     f'<strong>{html.escape(title)}{badge}</strong><small>{html.escape(item.get("venue",""))}</small>'
                     '</span><span class="reader-toc-arrow" aria-hidden="true">'+('→' if entry.get('page_links') else '↗')+'</span></a>')
    label=('今日论文目录' if entry.get('view')=='today' else
           '论文分类目录' if entry.get('collection') else '本期论文目录')
    classes='reader-toc reader-today-toc' if entry.get('view')=='today' else 'reader-toc'
    return (f'<nav class="{classes}" aria-label="{label}">'
            f'<div class="reader-section-label"><span>论文目录</span><span>{len(cards):02d} PAPERS</span></div>'
            '<div class="reader-toc-grid">'+''.join(cards)+'</div></nav>')


def article_cards(entry):
    # Saved HTML is the publication record; preserve the scientific copy verbatim.
    cards=saved_cards(entry)
    result=[]
    for index,(content,item) in enumerate(zip(cards,issue_items(entry)),1):
        content=re.sub(r'\sstyle=(?:"[^"]*"|\'[^\']*\')','',content)
        content=re.sub(r'<div class=\'english-copy title-copy\'([^>]*)>(.*?)</div>',
                       r'<h2 class="english-copy title-copy"\1>\2</h2>',content,count=1,flags=re.S)
        # These old nested tables contain layout cells, not scientific data tables.
        content=re.sub(r'</?(?:table|tbody|thead|tr|td)\b[^>]*>','',content,flags=re.I)
        content=re.sub(r'<p>PAPER \d+</p>',f'<p class="reader-paper-number">PAPER {index:02d}</p>',content,count=1)
        content=re.sub(r'^论文\s*\d+',f'论文 {index:02d}',content,count=1)
        content=re.sub(r'(<h4>Authors\s.*?)(?=<h4>Study overview\s)',
                       r'<details class="reader-metadata"><summary>论文信息与作者 <span>Paper details & affiliations</span></summary><div>\1</div></details>',
                       content,count=1,flags=re.S)
        if not item.get('bilingual'):
            content=re.sub(r'(<p><strong>作者：.*?)(?=<p>内容概括</p>)',
                           r'<details class="reader-metadata"><summary>论文信息与作者 <span>Paper details & affiliations</span></summary><div>\1</div></details>',
                           content,count=1,flags=re.S)
            for label in ('内容概括','研究思路与证据链','我的综合解读','推荐理由与创新点（详细）','应用前景（潜在）','未来可能方向（展望）'):
                content=content.replace('<p>'+label+'</p>','<h4>'+label+'</h4>')
        # Replace the old original/supporting-source buttons with a plain DOI.
        content=re.sub(r'<p\b[^>]*>\s*(?:<a\b[^>]*>.*?</a>\s*)+</p>','',content,flags=re.S|re.I)
        content=re.sub(r'<a\b[^>]*>(.*?)</a>',r'\1',content,flags=re.S|re.I)
        key=paper_key(item)
        doi=key[4:] if key.startswith('doi:') else '未提供 / Not provided'
        updates=entry.get('paper_updates',[])
        updated_on=updates[index-1] if index<=len(updates) else ''
        publication=(f'<footer class="reader-publication"><p>DOI: <span class="reader-doi">{html.escape(doi)}</span></p>'
                     +('<p>更新到网站 / Website updated: <time datetime="'+updated_on+'">'+updated_on+'</time>（北京时间）</p>'
                       if updated_on else '<p>更新到网站：日期待记录</p>')+'</footer>')
        kind=TYPE_LABELS.get(paper_type(item),'类型待核实')
        direction=DIRECTION_LABELS[paper_direction(item)]
        back_link=('' if entry.get('view')=='paper' else
                   '<a class="reader-back-top" href="#reading-top" target="_self">'
                   +('返回顶部 ↑' if entry.get('view')=='today' else '返回目录 ↑')+'</a>')
        result.append(f'<article class="reading-paper" id="reading-paper-{index}">'
                      f'<div class="reader-paper-meta"><span>{html.escape(item.get("venue",""))}</span>'
                      f'<div class="reader-classification"><span>{html.escape(kind)}</span>'
                      f'<span>{html.escape(direction)}</span></div></div>'+content
                      +publication+back_link+'</article>')
    return result


def page_css(root,theme):
    variables=';'.join('--reading-'+key+':'+value for key,value in theme.items())
    return ':root{'+variables+'}'+(Path(root)/'assets/streamlit-reader.css').read_text(encoding='utf-8')


def navigation_script(root):
    return (Path(root)/'assets/reading-navigation.js').read_text(encoding='utf-8')


def standalone(entry,image,css):
    title='论文分类精读库' if entry.get('collection') else '每日论文精读 · '+entry['day']
    return ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>'+title+'</title><style>'+css+'</style></head>'
            '<body class="reader-export"><main>'+hero(entry,image)+(table_of_contents(entry) if entry.get('view')!='today' else '')
            +''.join(article_cards(entry))+'</main><script>'+navigation_script(Path(__file__).parent)+'</script></body></html>')
