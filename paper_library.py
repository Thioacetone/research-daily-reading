"""Classify and deduplicate published papers without changing their content."""
import re
import unicodedata
from urllib.parse import unquote

TYPE_LABELS={'all':'全部类型','review':'综述','research':'非综述'}
DIRECTION_LABELS={
    'drug-discovery':'药物发现与作用机制',
    'cadd-aidd':'CADD/AIDD 与计算药物发现',
    'protein-degradation':'靶向蛋白降解',
    'neuropharmacology':'抑郁症与神经药理',
    'bioorthogonal':'生物正交反应',
    'chemical-probes':'化学探针与共价配体',
    'chemical-biology':'化学生物学',
    'other':'其他／待分类',
}


def saved_cards(entry):
    if 'saved_cards' in entry:
        cards=list(entry['saved_cards'])
    else:
        cards=re.findall(r'<div\b[^>]*class=[\'"]reading-copy[\'"][^>]*>(.*?)</div></td></tr></table>',
                         entry['document'],flags=re.S)
    if len(cards)!=entry['count']:
        raise ValueError('Saved reading page does not contain every article')
    return cards


def paper_type(item):
    value=item.get('recommendation_kind','').casefold()
    if value in ('review','research'):
        return value
    label=item.get('kind','').strip().casefold()
    if label in ('综述','review','review article','systematic review','meta-analysis'):
        return 'review'
    if label in ('研究论文','研究性文章','research','research article','article'):
        return 'research'
    return 'other'


def paper_direction(item):
    declared=item.get('research_direction')
    if declared in DIRECTION_LABELS:
        return declared
    # Infer only from the paper's own title, not speculative future applications.
    title=(item.get('paper_title') or item.get('title') or '').casefold()
    for direction,pattern in (
        ('bioorthogonal',r'bioorthogonal|bio-orthogonal|staudinger ligation|click-to-release|tetrazine'),
        ('cadd-aidd',r'docking|virtual screening|computer.aided|deep learning|generative|swissadme'),
        ('neuropharmacology',r'psychedelic|psychoplastogen|hallucinogen|antidepressant|neural plasticity|depression'),
        ('protein-degradation',r'degrad|protac|lytac'),
        ('chemical-probes',r'covalent ligand|chemical probe|chemoproteom'),
        ('drug-discovery',r'drug discovery|drug design'),
        ('chemical-biology',r'chemical biology')):
        if re.search(pattern,title):
            return direction
    return 'other'


def paper_key(item):
    doi=unquote(str(item.get('doi') or '')).strip().casefold()
    doi=re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)','',doi)
    if doi:
        return 'doi:'+doi
    title=item.get('paper_title') or item.get('title') or item.get('title_zh') or ''
    title=' '.join(unicodedata.normalize('NFKC',title).casefold().split())
    if not title:
        raise ValueError('Paper has neither DOI nor title')
    return 'title:'+title


def build_paper_library(reports):
    records=[];seen=set()
    for entry in sorted(reports,key=lambda entry:(entry['day'],str(entry.get('file',''))),reverse=True):
        items=[item for section in entry['report']['sections'].values() for item in section['items']]
        for item,content in zip(items,saved_cards(entry)):
            key=paper_key(item)
            if key in seen:
                continue
            seen.add(key)
            records.append({'key':key,'item':item,'content':content,'day':entry['day'],
                            'type':paper_type(item),'direction':paper_direction(item)})
    return records


def filter_papers(records,kind='all',direction='all'):
    return [record for record in records
            if (kind=='all' or record['type']==kind)
            and (direction=='all' or record['direction']==direction)]


def as_collection(records):
    return {'collection':True,'count':len(records),'day':max((r['day'] for r in records),default=''),
            'saved_cards':[record['content'] for record in records],
            'report':{'edition':'paper-recommendation','sections':{'library':{'items':[r['item'] for r in records]}}}}
