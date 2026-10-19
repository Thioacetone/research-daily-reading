"""Present saved scientific copy as a continuous reading page."""
import base64
from datetime import date
import html
import mimetypes
from pathlib import Path
import re


def image_data(path):
    path=Path(path)
    mime=mimetypes.guess_type(path.name)[0] or 'image/jpeg'
    return 'data:'+mime+';base64,'+base64.b64encode(path.read_bytes()).decode('ascii')


def issue_items(entry):
    return [item for section in entry['report']['sections'].values() for item in section['items']]


def hero(entry,image):
    day=date.fromisoformat(entry['day'])
    weekday=('周一','周二','周三','周四','周五','周六','周日')[day.weekday()]
    return (f'<header class="reader-hero" id="reading-top"><div class="reader-hero-copy">'
            f'<p class="reader-eyebrow">DAILY READING <span> / </span> {day:%Y.%m.%d} · {weekday}</p>'
            '<h1>每日论文精读<span class="reader-heading-dot">.</span></h1>'
            '<p class="reader-intro">把值得读的论文，读得更深一点。</p>'
            '<div class="reader-topics"><span>化学生物学</span><span>药物发现</span>'
            '<span>CADD / AIDD</span><span>生物正交</span></div>'
            '</div><figure class="reader-hero-art">'
            f'<img src="{image_data(image)}" alt="本次阅读配图"></figure></header>')


def table_of_contents(entry):
    cards=[]
    for index,item in enumerate(issue_items(entry),1):
        value=item.get('bilingual',{})
        title=value.get('title_zh') or item.get('title_zh') or item.get('paper_title') or item['title']
        cards.append(f'<a class="reader-toc-item" href="#reading-paper-{index}" target="_self">'
                     f'<span class="reader-toc-number">{index:02d}</span><span class="reader-toc-copy">'
                     f'<strong>{html.escape(title)}</strong><small>{html.escape(item.get("venue",""))}</small>'
                     '</span><span class="reader-toc-arrow" aria-hidden="true">↗</span></a>')
    return ('<nav class="reader-toc" aria-label="本期论文目录">'
            f'<div class="reader-section-label"><span>本期阅读</span><span>{len(cards):02d} PAPERS</span></div>'
            '<div class="reader-toc-grid">'+''.join(cards)+'</div></nav>')


def article_cards(entry):
    # Saved HTML is the publication record; preserve the scientific copy verbatim.
    cards=re.findall(r'<div\b[^>]*class=[\'"]reading-copy[\'"][^>]*>(.*?)</div></td></tr></table>',
                     entry['document'],flags=re.S)
    if len(cards)!=entry['count']:
        raise ValueError('Saved reading page does not contain every article')
    result=[]
    for index,(content,item) in enumerate(zip(cards,issue_items(entry)),1):
        content=re.sub(r'\sstyle=(?:"[^"]*"|\'[^\']*\')','',content)
        content=re.sub(r'<div class=\'english-copy title-copy\'([^>]*)>(.*?)</div>',
                       r'<h2 class="english-copy title-copy"\1>\2</h2>',content,count=1,flags=re.S)
        # These old nested tables contain layout cells, not scientific data tables.
        content=re.sub(r'</?(?:table|tbody|thead|tr|td)\b[^>]*>','',content,flags=re.I)
        content=re.sub(r'(<p>)PAPER (\d+)(</p>)',r'<p class="reader-paper-number">PAPER \2</p>',content,count=1)
        content=re.sub(r'(<h4>Authors\s.*?)(?=<h4>Study overview\s)',
                       r'<details class="reader-metadata"><summary>论文信息与作者 <span>Paper details & affiliations</span></summary><div>\1</div></details>',
                       content,count=1,flags=re.S)
        if not item.get('bilingual'):
            content=re.sub(r'(<p><strong>作者：.*?)(?=<p>内容概括</p>)',
                           r'<details class="reader-metadata"><summary>论文信息与作者 <span>Paper details & affiliations</span></summary><div>\1</div></details>',
                           content,count=1,flags=re.S)
            for label in ('内容概括','研究思路与证据链','我的综合解读','推荐理由与创新点（详细）','应用前景（潜在）','未来可能方向（展望）'):
                content=content.replace('<p>'+label+'</p>','<h4>'+label+'</h4>')
        content=re.sub(r'(<a\b)(?![^>]*\btarget=)',r'\1 target="_blank" rel="noopener noreferrer"',content)
        result.append(f'<article class="reading-paper" id="reading-paper-{index}">'
                      f'<div class="reader-paper-meta"><span>{html.escape(item.get("venue",""))}</span>'
                      f'<span>{html.escape(item.get("kind",""))}</span></div>'+content
                      +'<a class="reader-back-top" href="#reading-top" target="_self">返回本期目录 ↑</a></article>')
    return result


def page_css(root,theme):
    variables=';'.join('--reading-'+key+':'+value for key,value in theme.items())
    return ':root{'+variables+'}'+(Path(root)/'assets/streamlit-reader.css').read_text(encoding='utf-8')


def standalone(entry,image,css):
    return ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>每日论文精读 · '+entry['day']+'</title><style>'+css+'</style></head>'
            '<body class="reader-export"><main>'+hero(entry,image)+table_of_contents(entry)
            +''.join(article_cards(entry))+'</main></body></html>')
