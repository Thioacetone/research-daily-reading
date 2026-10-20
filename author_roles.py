"""Read author roles; default to the last author when correspondence is absent."""
import re
import json
from pathlib import Path
import unicodedata
from html.parser import HTMLParser
from xml.etree import ElementTree as ET


def name_key(value):
    return ' '.join(unicodedata.normalize('NFC', value).casefold().split())


INSTITUTIONS_PATH = Path(__file__).resolve().with_name('institution_names.json')
DEPARTMENTS_PATH = Path(__file__).resolve().with_name('department_names.json')
COUNTRIES_PATH = Path(__file__).resolve().with_name('affiliation_countries.json')


def unit_has_detail(value):
    university=bool(re.search(r'\bUniversit\w*\b|大学',value,re.I))
    detail_value=value
    if not university:
        try:
            aliases=json.loads(INSTITUTIONS_PATH.read_text(encoding='utf-8'))
            normalized=name_key(value)
            matched=[name_key(name) for name,translation in aliases.items()
                     if isinstance(translation,str) and re.search(r'大学|理工学院',translation)
                     and normalized.startswith(name_key(name))]
            university=bool(matched)
            if matched:detail_value=normalized[len(max(matched,key=len)):]
        except (OSError,ValueError,TypeError):pass
    if not university:
        return bool(value.strip())  # An independent institute/company is a unit.
    return bool(re.search(r'\b(?:School|College|Faculty|Department|Dept|Division|Institute|Institut|Instituto|Laboratory|Center|Centre|Program|Programme|Chair|Fakultät|Facultad|Departamento|Département)\b|学院|学系|研究科|学部|研究[所院]|中心|医院|实验室',detail_value,re.I))


def affiliation_country(original):
    """Use the published address before an institution's usual home country."""
    aliases={
        'USA':'美国','U.S.A.':'美国','United States':'美国','United States of America':'美国',
        'UK':'英国','United Kingdom':'英国','England':'英国','Scotland':'英国','Wales':'英国',
        'Japan':'日本','India':'印度','Germany':'德国','France':'法国','Italy':'意大利',
        'Canada':'加拿大','Australia':'澳大利亚','Israel':'以色列','Singapore':'新加坡',
        'Switzerland':'瑞士','Sweden':'瑞典','Denmark':'丹麦','Netherlands':'荷兰',
        'Spain':'西班牙','España':'西班牙','Austria':'奥地利','Finland':'芬兰','Norway':'挪威','Belgium':'比利时',
        'Malaysia':'马来西亚','Thailand':'泰国','Indonesia':'印度尼西亚','Vietnam':'越南',
        'Portugal':'葡萄牙','Greece':'希腊','Czech Republic':'捷克','Czechia':'捷克',
        'Hungary':'匈牙利','Romania':'罗马尼亚','Türkiye':'土耳其','Turkey':'土耳其',
        'Iran':'伊朗','Pakistan':'巴基斯坦','Egypt':'埃及','Argentina':'阿根廷','Chile':'智利',
        'Ireland':'爱尔兰','Iceland':'冰岛','Luxembourg':'卢森堡','Slovenia':'斯洛文尼亚',
        'New Zealand':'新西兰','South Korea':'韩国','Republic of Korea':'韩国',
        'Saudi Arabia':'沙特阿拉伯','Russia':'俄罗斯','Russian Federation':'俄罗斯',
        'Brazil':'巴西','Mexico':'墨西哥','South Africa':'南非','Poland':'波兰','Bulgaria':'保加利亚',
        'China':'中国','P.R. China':'中国','People’s Republic of China':'中国',
        'Taiwan':'中国台湾','Hong Kong':'中国香港','Macao':'中国澳门','Macau':'中国澳门'}
    matches=[]
    for segment in re.finditer(r'[^,;，；]+',original):
        part=segment.group()
        if re.search(r'\b(?:University|Universit\w*|School|College|Faculty|Department|Institute|Laboratory|Academy|Center|Centre)\b',part,re.I):
            continue
        for alias,label in aliases.items():
            for match in re.finditer(r'(?<![A-Za-z])'+re.escape(alias)+r'(?![A-Za-z])',part,re.I):
                matches.append((segment.start()+match.end(),len(alias),label))
    if matches:return max(matches)[2]
    # Some publisher deposits flatten a full address without commas. These
    # explicit postal country abbreviations are not university-name guesses.
    trailing=re.search(r'(?:^|\s)(USA|U\.S\.A\.|UK)\s*[.;]?\s*$',original,re.I)
    if trailing:return '英国' if trailing.group(1).upper()=='UK' else '美国'
    try:
        countries=json.loads(COUNTRIES_PATH.read_text(encoding='utf-8'))
    except (OSError,ValueError):return ''
    parts=[name_key(p) for p in re.split(r'[,;，；]',original) if p.strip()]
    found=[label for name,label in countries.items() if name_key(name) in parts or name_key(name)==name_key(original)]
    return found[0] if len(set(found))==1 else ''


def unit_translation_valid(original, translated):
    """A university-only translation cannot stand in for a deposited school."""
    if not isinstance(translated, str) or not re.search(r'[\u4e00-\u9fff]', translated):
        return False
    if re.search(r'(?<!\d)\d{3,6}(?!\d)|\b(?:Street|Road|Avenue|Blvd|Suite|Kagamiyama|Qianjin|Xueyuan)\b',translated,re.I):
        return False
    labels = [(r'\b(?:School|College|Faculty)\s+of\b', r'学院|研究生院|研究科|学部'),
              (r'\bDepartment\s+of\b', r'系'),
              (r'\b(?:Center|Centre)\s+for\b', r'中心')]
    return all(not re.search(source, original, re.I) or re.search(target, translated)
               for source, target in labels)


def merge_author_affiliations(existing, incoming):
    """Prefer an explicitly mapped, more specific unit without pooling authors."""
    result = [{'name': p['name'], 'institutions': list(p.get('institutions', []))} for p in existing]
    for pair in incoming:
        target = next((p for p in result if name_key(p['name']) == name_key(pair['name'])), None)
        if target is None:
            target = {'name': pair['name'], 'institutions': []}
            result.append(target)
        for unit in pair.get('institutions', []):
            if unit in target['institutions']:
                continue
            broad = lambda value: not re.search(r'\b(?:School|College|Faculty|Department|Institute|Laboratory|Center|Centre)\b|学院|系|研究所|中心', value, re.I)
            def contains(parent, child):
                base = name_key(parent.split(',', 1)[0])
                components = [name_key(part) for part in re.split(r'[,;，；]', child)]
                return bool(base and base in components and
                            (name_key(child).startswith(name_key(parent)+',') or (broad(parent) and not broad(child))))
            if any(contains(unit, old) for old in target['institutions']):
                continue
            target['institutions'] = [old for old in target['institutions'] if not contains(old, unit)]
            target['institutions'].append(unit)
    return result


def known_unit_translations(units):
    try:
        names = json.loads(INSTITUTIONS_PATH.read_text(encoding='utf-8'))
        lookup = {name_key(key): value for key, value in names.items()
                  if isinstance(value, str) and re.search(r'[\u4e00-\u9fff]', value)}
        departments = json.loads(DEPARTMENTS_PATH.read_text(encoding='utf-8'))
        detail_lookup = {name_key(key): value for key, value in departments.items()}
        result = {}
        for unit in units:
            key = name_key(unit)
            if key in lookup:
                result[unit] = lookup[key]
                continue
            # Match a verified institution followed by its address, not a substring
            # elsewhere in an affiliation or an unrelated branch/campus.
            parts = [part.strip() for part in re.split(r'[,;，；]', unit) if part.strip()]
            roots=[];covered=set()
            for width in (3,2,1):
                for start in range(len(parts)-width+1):
                    positions=set(range(start,start+width))
                    key=name_key(', '.join(parts[start:start+width]))
                    if not positions&covered and key in lookup:
                        roots.append(lookup[key]);covered.update(positions)
            details = [detail_lookup[name_key(p)] for p in parts if name_key(p) in detail_lookup]
            details.sort(key=lambda s:0 if re.search(r'学院|研究生院|研究科|学部',s) else 1 if s.endswith('系') else 2)
            unknown_details = [p for index,p in enumerate(parts) if index not in covered and re.search(r'\b(?:School|College|Faculty|Department|Institute|Laboratory|Center|Centre)\b', p, re.I)
                               and name_key(p) not in lookup and name_key(p) not in detail_lookup]
            if roots and not unknown_details:
                translated = ''.join(dict.fromkeys(roots + details))
                if unit_translation_valid(unit, translated):
                    result[unit] = translated
        return result
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


def display_unit_names(item):
    names = (item.get('first_authors') or item.get('people', [])[:1]) + (
        item.get('corresponding_authors') or item.get('people', [])[-1:])
    keys = {name_key(name) for name in names}
    units = []
    for pair in item.get('author_affiliations', []):
        if name_key(pair['name']) in keys:
            units.extend(unit for unit in pair.get('institutions', []) if unit and unit not in units)
    return units


def unit_display(original, translations):
    chinese = translations.get(original)
    if unit_translation_valid(original, chinese):
        # The email shows the institution and academic unit, not street addresses.
        chinese = re.sub(r'（[A-Za-z0-9& .-]+）|\([A-Za-z0-9& .-]+\)', '', chinese).strip()
        parts = [p.strip() for p in re.split(r'[,，;；]', chinese) if p.strip()]
        universities = [p for p in parts if '大学' in p]
        chinese = ''.join(universities + [p for p in parts if p not in universities])
        if '大学' in chinese and not re.search(r'学院|系|研究科|研究[所院]|中心|医院|实验室|研究生项目|学部', chinese.split('大学', 1)[1]):
            chinese += '（院系待原文核实）'
        elif chinese == '中国科学院':
            chinese += '（下属单位未披露）'
        country=affiliation_country(original)
        return (country+'·' if country and country!='中国' else '')+chinese
    return original


def role_units(item, names):
    """Only use a verified per-author affiliation mapping, not the pooled list."""
    pairs = item.get('author_affiliations', [])
    translations = dict(item.get('institutions_zh') or {})
    translations.update(known_unit_translations(display_unit_names(item)))
    result = []
    seen = set()
    for name in names:
        key = name_key(name)
        if not key or key in seen:
            continue
        seen.add(key)
        units = []
        for pair in pairs:
            if name_key(pair['name']) == key:
                units.extend(unit for unit in pair.get('institutions', []) if unit and unit not in units)
        displayed = list(dict.fromkeys(unit_display(unit, translations) for unit in units))
        result.append(name + '：' + ('；'.join(displayed) or '工作单位未明确提供'))
    return '；'.join(result)


def author_unit_fields(item):
    first = item.get('first_authors') or item.get('people', [])[:1]
    corresponding = item.get('corresponding_authors', [])
    label = '通讯作者及工作单位'
    if not corresponding and item.get('people'):
        corresponding = item['people'][-1:]
        label += '（默认末位作者）'
    return [('第一作者及工作单位', role_units(item, first) or '第一作者未明确提供'),
            (label, role_units(item, corresponding) or '作者信息未明确提供')]


class AffiliationPage(HTMLParser):
    """Read named author blocks and explicit affiliation anchors only."""
    VOID = {'meta','link','img','br','hr','input','source','wbr','area','base','embed','param'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.captures = []
        self.author = None
        self.blocks = []
        self.units = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in self.VOID:
            return
        depth = len(self.stack)
        classes = attrs.get('class', '').lower().split()
        self.stack.append(tag)
        explicit_name = attrs.get('data-author-name', '')
        if self.author is None and (explicit_name or any(c in classes for c in ('author-info','author-item','contributor'))):
            self.author = {'name':explicit_name, 'institutions':[], 'refs':[], 'depth':depth}
        unit_id = attrs.get('id','')
        affiliation = any('affiliation' in c for c in classes)
        if unit_id and (affiliation or re.fullmatch(r'(?:aff|affiliation)[-_]?\d+',unit_id,re.I)):
            self.captures.append({'kind':'unit', 'id':unit_id, 'depth':depth, 'text':[]})
        if self.author:
            if any(c in ('author-name','authorname','contrib-name','name') for c in classes):
                self.captures.append({'kind':'name','depth':depth,'text':[]})
            if affiliation:
                self.captures.append({'kind':'aff','depth':depth,'text':[]})
            href = attrs.get('href','')
            if href.startswith('#') and (attrs.get('ref-type') == 'aff' or re.fullmatch(r'#(?:aff|affiliation)[-_]?\d+',href,re.I)):
                self.author['refs'].append(href[1:])
            self.author['refs'].extend(attrs.get('data-affiliation-ids','').split())

    def handle_data(self, value):
        for capture in self.captures:
            capture['text'].append(value)

    def handle_endtag(self, tag):
        if tag not in self.stack:
            return
        depth = len(self.stack) - 1 - self.stack[::-1].index(tag)
        closed = [capture for capture in self.captures if capture['depth'] >= depth]
        self.captures = [capture for capture in self.captures if capture['depth'] < depth]
        for capture in closed:
            value = ' '.join(' '.join(capture['text']).split()).strip()
            if not value:
                continue
            if capture['kind'] == 'unit':
                self.units[capture['id']] = value
            elif self.author and capture['kind'] == 'name':
                self.author['name'] = value
            elif self.author and capture['kind'] == 'aff':
                self.author['institutions'].append(value)
        if self.author and self.author['depth'] >= depth:
            self.blocks.append(self.author)
            self.author = None
        del self.stack[depth:]


def html_affiliations(data, authors):
    page = AffiliationPage()
    page.feed(data.decode('utf-8',errors='replace'))
    known = {name_key(name): name for name in authors}
    result = []
    for block in page.blocks:
        name = known.get(name_key(block['name']))
        units = block['institutions'] + [page.units[ref] for ref in block['refs'] if ref in page.units]
        if name and units:
            result.append({'name':name,'institutions':list(dict.fromkeys(units))})
    return result


def jats_roles(data):
    """Read author-order and corresp declarations only from JATS article front."""
    empty = {'authors': [], 'first_authors': [], 'corresponding_authors': [], 'author_affiliations': []}
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        return empty
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return empty
    tag = lambda node: node.tag.rsplit('}', 1)[-1]
    if tag(root) != 'article':
        return empty
    front = next((node for node in root if tag(node) == 'front'), None)
    if front is None:
        return empty
    meta = next((node for node in front if tag(node) == 'article-meta'), None)
    if meta is None:
        return empty
    text = lambda node: ' '.join(' '.join(node.itertext()).split())
    units = {}
    for node in meta.iter():
        if tag(node) == 'aff' and node.get('id'):
            parts = [node.text or '']
            for child in node:
                if tag(child) not in ('label','institution-id','email'):
                    if tag(child)=='country' and ''.join(parts).strip().rstrip().endswith(',') is False:
                        parts.append(', ')
                    parts.append(text(child))
                parts.append(child.tail or '')
            units[node.get('id')] = ' '.join(' '.join(parts).split())
    corresp_ids = {node.get('id') for node in meta.iter() if tag(node) == 'corresp' and node.get('id')}
    for notes in meta:
        if tag(notes) == 'author-notes':
            corresp_ids.update(node.get('id') for node in notes if node.get('id')
                              and (any(tag(child) == 'email' for child in node.iter())
                                   or re.search(r'\bcorresponding author\b|\bcorrespondence\b', text(node), re.I)))
    names, correspondents, pairs = [], [], []
    for group in meta:
        if tag(group) != 'contrib-group':
            continue
        shared=[node for node in group if tag(node)=='aff' and node.get('id') in units]
        # One unnumbered address printed for one group applies to that group.
        # Never use this fallback when any author has a numbered affiliation.
        shared_unit=(units[shared[0].get('id')] if len(shared)==1
                     and not any(tag(n)=='xref' and n.get('ref-type')=='aff' for n in group.iter()) else '')
        for contrib in group:
            if tag(contrib) != 'contrib' or not (contrib.get('contrib-type') == 'author'
                    or (contrib.get('contrib-type') is None and group.get('content-type') == 'author')):
                continue
            name_node = next((n for n in contrib if tag(n) == 'name'), None)
            if name_node is not None:
                given = next((text(n) for n in name_node if tag(n) == 'given-names'), '')
                family = next((text(n) for n in name_node if tag(n) == 'surname'), '')
                name = ' '.join(filter(None, (given, family)))
            else:
                name = next((text(n) for n in contrib if tag(n) in ('string-name', 'collab')), '')
            if not name:
                continue
            names.append(name)
            affiliations = []
            is_corresp = contrib.get('corresp', '').lower() in ('yes', 'true', '1')
            for node in contrib.iter():
                if tag(node) == 'xref':
                    ids = node.get('rid', '').split()
                    if node.get('ref-type') == 'aff':
                        affiliations.extend(units[i] for i in ids if units.get(i) and units[i] not in affiliations)
                    elif node.get('ref-type') in ('corresp','author-notes') and any(i in corresp_ids for i in ids):
                        is_corresp = True
                elif tag(node) == 'aff' and text(node):
                    affiliations.append(text(node))
            if not affiliations and shared_unit:affiliations=[shared_unit]
            if affiliations:
                pairs.append({'name': name, 'institutions': affiliations})
            if is_corresp:
                correspondents.append(name)
    return {'authors': names, 'first_authors': names[:1], 'corresponding_authors': correspondents, 'author_affiliations': pairs}


def meta_correspondents(meta, authors):
    """A correspondence tag must name an actual author, not just an email."""
    known = {name_key(name): name for name in authors}
    names = []
    for key in ('citation_corresponding_author', 'citation_corresponding_authors'):
        for value in meta.get(key, []):
            for name in re.split(r';|\|', value):
                actual = known.get(name_key(name))
                if actual and actual not in names:
                    names.append(actual)
    return names
