"""Conservative display formatting; never change the stored research evidence.

Formula counts, explicit charges, hybridization and unit powers are distinct.
Ambiguous labels and charges stay as supplied rather than being inferred.
"""
import html
import re

ELEMENTS = frozenset("H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og".split())
ELEMENT = "(?:" + "|".join(sorted(ELEMENTS, key=lambda x: (-len(x), x))) + ")"
COUNT = r"(?:[0-9]+(?:\.[0-9]+)?)"
ATOM = ELEMENT + COUNT + "?"  # count quantifier belongs to the whole group
PAREN = r"\((?:" + ATOM + r")+\)"
GROUP = r"(?:" + PAREN + r"|\[(?:" + ATOM + "|" + PAREN + COUNT + r"?)+\])" + COUNT + "?"
BASE = "(?:" + ATOM + "|" + GROUP + ")+"
FORMULA = re.compile(r"(?<![A-Za-z0-9_])" + BASE + r"(?:[·⋅][0-9]*" + BASE + r")*(?![A-Za-z0-9_])")
PROTECTED = re.compile(r"(?:https?://|www\.)\S+|\b10\.\d{4,9}/\S+")
SUB = str.maketrans("0123456789+-", "₀₁₂₃₄₅₆₇₈₉₊₋")
SUP = str.maketrans("0123456789+-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻")
SUB_CHARS = "₀₁₂₃₄₅₆₇₈₉₊₋"
SUP_CHARS = "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻"
SCRIPTS = re.compile("([" + SUB_CHARS + "]+(?:\\.[" + SUB_CHARS + "]+)*)|([" + SUP_CHARS + "]+)")
SIGNS = {"+": "+", "-": "-", "−": "-", "–": "-"}
# Uncharged single-element labels such as C3 (complement protein) are ambiguous.
MOLECULES = {"H2", "N2", "O2", "O3", "F2", "Cl2", "Br2", "I2", "S8", "P4", "C60", "C70"}
MOLECULAR_ELEMENTS = {"H", "N", "O", "F", "Cl", "Br", "I", "S", "P", "C"}
HYBRID = re.compile(r"(?<![A-Za-z0-9_])sp\s*(?:\^\s*)?([23])(?![A-Za-z0-9_])")
UNIT_POWER = re.compile(r"(?<![A-Za-z0-9_])(nm|μm|µm|mm|cm|m|mg|kg|g|ms|s|min|h|mol|mmol|K|mL|L)(?:\^?([−–-][1-9][0-9]?)|\^([234]))(?![A-Za-z0-9_])")
AREA_VOLUME = re.compile(r"(?<![A-Za-z0-9_])(nm|μm|µm|mm|cm|m)([23])(?![A-Za-z0-9_])")
SPACED_ATOM = ELEMENT + r"(?:[ \t]*" + COUNT + r")?"
# Publisher markup sometimes becomes 'H 2 CO 3'. Allow spaces before
# counts and a bridge after a count; never merge prose such as 'As CO2'.
BRIDGE = r"(?<=[0-9])[ \t]+(?=(?:" + ELEMENT + r")+[ \t]*[0-9]|[A-Z](?![A-Za-z]))"
SPACED_FORMULA = re.compile(r"(?<![A-Za-z0-9_])(?:" + SPACED_ATOM + r")+(?:" + BRIDGE + r"(?:" + SPACED_ATOM + r")+)*(?![A-Za-z0-9_])")


def _formula(match, text):
    value = match.group()
    end = match.end()
    # Only a directly attached sign, not the '+' separating two reactants.
    charge = re.match(r"(?:\^([1-9][0-9]?)?([+−–-])|([+−–-]))(?![A-Za-z0-9_])", text[end:])
    # Locants such as 6-O-sulfation / 6-O-硫酸化 use naming hyphens.
    # They do not turn the oxygen or nitrogen into an anion.
    if charge and not charge.group().startswith('^') and re.search(r"\d+[−–-]$",text[:match.start()]):
        charge=None
    # A bond to a Chinese atom/group name is not an ionic charge (C–卤素).
    if charge and re.match(r"[–−-](?:硫酸|磷酸|酰|聚糖|糖|卤素|卤原子|杂原子|金属|碳|氮|氧|氢|硼|硅|(?:二|三|四)?(?:甲|乙|丙|丁|苯|羟|氨|硝|羧))",text[end:]):
        charge=None
    if charge and not charge.group().startswith('^') and re.search(r"[0-9]{2,}$", value) and not re.search(r"\][0-9]+$", value):
        # SO42- might have lost the separation between count and charge.
        return value, end
    element_counts = re.fullmatch("(" + ELEMENT + ")(" + COUNT + ")?", value)
    if element_counts:
        element, count = element_counts.groups()
        if charge and not charge.group().startswith("^") and count:
            # O2- / H2+ can denote either a molecular ion or a lost charge
            # superscript. Do not silently choose either chemical identity.
            if element in MOLECULAR_ELEMENTS or not count.isdigit() or not 2 <= int(count) <= 8:
                return value, end
            return element + (count + SIGNS[charge.group(3)]).translate(SUP), end + charge.end()
        if count and value not in MOLECULES:
            return value, end
    numbers = re.findall(COUNT, value)
    if any(float(n) > 999 for n in numbers):
        return value, end
    formatted = re.sub(COUNT, lambda m: m.group().translate(SUB), value)
    # Hydrate coefficients are ordinary baseline numbers: ·5H₂O.
    formatted = re.sub(r"([·⋅])([₀₁₂₃₄₅₆₇₈₉]+)",
                       lambda m: m[1] + m[2].translate(str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")), formatted)
    if charge:
        if charge.group(1) or charge.group().startswith("^"):
            power = (charge.group(1) or "") + SIGNS[charge.group(2)]
        else:
            power = SIGNS[charge.group(3)]
            # A charge after a square-bracketed coordination entity is clear.
            bracket = re.search(r"\]([1-9][0-9]?)$", value)
            if bracket:
                formatted = formatted[:-len(bracket[1])]
                power = bracket[1] + power
        formatted += power.translate(SUP)
        end += charge.end()
    return formatted, end


def _format_segment(text):
    def join_spaced(match):
        candidate = re.sub(r"[ \t]+", "", match.group())
        formula = FORMULA.fullmatch(candidate)
        if formula:
            # Require a meaningful count/charge before removing any spaces.
            rendered, _ = _formula(formula, candidate + text[match.end():match.end()+4])
            if rendered != candidate:
                return candidate
        return match.group()

    text = SPACED_FORMULA.sub(join_spaced, text)
    pieces, cursor = [], 0
    for match in FORMULA.finditer(text):
        if match.start() < cursor:
            continue
        value, end = _formula(match, text)
        pieces.extend((text[cursor:match.start()], value))
        cursor = end
    pieces.append(text[cursor:])
    result = "".join(pieces)
    # Organic A-site abbreviations in common lead/tin halide perovskites.
    result=re.sub(r"(?<![A-Za-z0-9_])((?:FA|MA)(?:Pb|Sn)(?:I|Br|Cl))[ \t]*([0-9]+)(?![A-Za-z0-9_])",
                  lambda m:m[1]+m[2].translate(SUB),result)
    result = HYBRID.sub(lambda m: "sp" + m[1].translate(SUP), result)
    result = UNIT_POWER.sub(lambda m: m[1] + (m[2] or m[3]).replace("−", "-").replace("–", "-").translate(SUP), result)
    return AREA_VOLUME.sub(lambda m: m[1] + m[2].translate(SUP), result)


def chemical_text(text):
    """Unicode fallback for plain-text mail; protect URLs and DOI identifiers."""
    pieces, cursor = [], 0
    for match in PROTECTED.finditer(text):
        pieces.extend((_format_segment(text[cursor:match.start()]), match.group()))
        cursor = match.end()
    pieces.append(_format_segment(text[cursor:]))
    return "".join(pieces)


def chemical_html(text):
    """Escape untrusted text, emitting only semantic sub/sup tags we generate."""
    text = chemical_text(text)
    pieces, cursor = [], 0
    for match in SCRIPTS.finditer(text):
        pieces.append(html.escape(text[cursor:match.start()]))
        tag, chars = ("sub", SUB_CHARS) if match[1] else ("sup", SUP_CHARS)
        baseline = match.group().translate(str.maketrans(chars, "0123456789+-"))
        if tag == "sup":
            baseline = baseline.replace("-", "−")
        pieces.append(f"<{tag}>{baseline}</{tag}>")
        cursor = match.end()
    pieces.append(html.escape(text[cursor:]))
    return "".join(pieces)
