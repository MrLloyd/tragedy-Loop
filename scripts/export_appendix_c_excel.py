from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "characters.json"
OUTPUT_PATH = ROOT / "docs" / "附录C角色表_友好能力实现跟踪.xlsx"


AREA_ZH = {
    "city": "都市",
    "school": "学校",
    "hospital": "医院",
    "shrine": "神社",
    "faraway": "远方",
}

ATTR_ZH = {
    "adult": "成人",
    "animal": "动物",
    "boy": "少年",
    "creation": "人造物",
    "female": "女性",
    "girl": "少女",
    "male": "男性",
    "plant": "植物",
    "sister": "妹妹",
    "student": "学生",
    "virtual": "虚拟",
}


def zh_area(value: object) -> str:
    if value is None:
        return ""
    return AREA_ZH.get(str(value), str(value))


def zh_attr(value: object) -> str:
    if value is None:
        return ""
    return ATTR_ZH.get(str(value), str(value))


def infer_slot(ability_id: str, fallback: int) -> int:
    tail = ability_id.rsplit(":", 1)[-1]
    return int(tail) if tail.isdigit() else fallback


def ability_text_by_slot(character: dict[str, object]) -> list[str]:
    texts = list(character.get("goodwill_ability_texts", []) or [])
    while len(texts) < 4:
        texts.append("")

    structured_items = character.get("goodwill_abilities", []) or []
    for index, ability in enumerate(structured_items, start=1):
        if not isinstance(ability, dict):
            continue
        slot = infer_slot(str(ability.get("ability_id", "")), index)
        if not 1 <= slot <= 4:
            continue
        if texts[slot - 1]:
            continue
        description = str(ability.get("description", "") or "").strip()
        if description:
            texts[slot - 1] = description
    return [str(item).strip() for item in texts[:4]]


def ability_requirements(character: dict[str, object]) -> list[object]:
    requirements = list(character.get("goodwill_ability_goodwill_requirements", []) or [])
    while len(requirements) < 4:
        requirements.append("")
    return requirements[:4]


def ability_once_per_loop(character: dict[str, object]) -> list[str]:
    once_flags = list(character.get("goodwill_ability_once_per_loop", []) or [])
    while len(once_flags) < 2:
        once_flags.append("")
    result: list[str] = []
    for value in once_flags[:2]:
        if value == "":
            result.append("")
        else:
            result.append("是" if bool(value) else "否")
    return result


def trait_text(character: dict[str, object]) -> str:
    parts: list[str] = []
    base_traits = [str(item).strip() for item in (character.get("base_traits", []) or []) if str(item).strip()]
    if base_traits:
        parts.append("基础特性：" + "、".join(base_traits))
    trait_rule = str(character.get("trait_rule", "") or "").strip()
    if trait_rule:
        parts.append(trait_rule)
    return "；".join(parts)


def forbidden_area_text(character: dict[str, object]) -> str:
    return "、".join(zh_area(item) for item in (character.get("forbidden_areas", []) or []))


def build_rows(characters: list[dict[str, object]]) -> list[list[object]]:
    rows: list[list[object]] = [[
        "角色名",
        "特性",
        "属性1",
        "属性2",
        "初始区域",
        "禁行区域",
        "友好能力1",
        "友好能力2",
        "友好能力3",
        "友好能力4",
        "不安限度",
        "友好能力1所需友好度",
        "友好能力2所需友好度",
        "友好能力3所需友好度",
        "友好能力4所需友好度",
        "能力1一轮回一次",
        "能力2一轮回一次",
    ]]

    for character in characters:
        attrs = [zh_attr(item) for item in (character.get("attributes", []) or [])]
        while len(attrs) < 2:
            attrs.append("")
        abilities = ability_text_by_slot(character)
        requirements = ability_requirements(character)
        once_flags = ability_once_per_loop(character)
        rows.append([
            character.get("name", ""),
            trait_text(character),
            attrs[0],
            attrs[1],
            zh_area(character.get("initial_area", "")),
            forbidden_area_text(character),
            abilities[0],
            abilities[1],
            abilities[2],
            abilities[3],
            character.get("paranoia_limit", ""),
            requirements[0],
            requirements[1],
            requirements[2],
            requirements[3],
            once_flags[0],
            once_flags[1],
        ])
    return rows


def col_letter(index: int) -> str:
    result = ""
    current = index
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        result = chr(65 + remainder) + result
    return result


def cell_xml(row_idx: int, col_idx: int, value: object, style_id: int) -> str:
    ref = f"{col_letter(col_idx)}{row_idx}"
    if value is None:
        value = ""
    if isinstance(value, bool):
        value = "是" if value else "否"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<c r="{ref}" s="{style_id}"><v>{value}</v></c>'
    text = escape(str(value))
    return f'<c r="{ref}" s="{style_id}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'


def worksheet_xml(rows: list[list[object]], widths: list[int]) -> str:
    max_col = max((len(row) for row in rows), default=1)
    max_row = max(len(rows), 1)
    end_ref = f"{col_letter(max_col)}{max_row}"
    cols_xml = "".join(
        f'<col min="{idx}" max="{idx}" width="{width}" customWidth="1"/>'
        for idx, width in enumerate(widths, start=1)
    )
    row_xml_parts: list[str] = []
    for row_idx, row in enumerate(rows, start=1):
        style_id = 1 if row_idx == 1 else 2
        cells = "".join(
            cell_xml(row_idx, col_idx, value, style_id)
            for col_idx, value in enumerate(row, start=1)
        )
        height_attr = ' ht="24" customHeight="1"' if row_idx == 1 else ""
        row_xml_parts.append(f'<row r="{row_idx}"{height_attr}>{cells}</row>')
    rows_xml = "".join(row_xml_parts)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<dimension ref="A1:{end_ref}"/>'
        '<sheetViews><sheetView workbookViewId="0">'
        '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
        '<selection pane="bottomLeft" activeCell="A2" sqref="A2"/>'
        '</sheetView></sheetViews>'
        '<sheetFormatPr defaultRowHeight="22"/>'
        f'<cols>{cols_xml}</cols>'
        f'<sheetData>{rows_xml}</sheetData>'
        f'<autoFilter ref="A1:{end_ref}"/>'
        '</worksheet>'
    )


def content_types_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/docProps/core.xml" '
        'ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        "</Types>"
    )


def root_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
        '</Relationships>'
    )


def workbook_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<bookViews><workbookView xWindow="240" yWindow="120" windowWidth="18000" windowHeight="9000"/></bookViews>'
        '<sheets><sheet name="角色表" sheetId="1" r:id="rId1"/></sheets>'
        '</workbook>'
    )


def workbook_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        '</Relationships>'
    )


def styles_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="2">'
        '<font><sz val="11"/><name val="Calibri"/><family val="2"/></font>'
        '<font><b/><sz val="11"/><name val="Calibri"/><family val="2"/></font>'
        '</fonts>'
        '<fills count="2">'
        '<fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill>'
        '</fills>'
        '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="3">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1">'
        '<alignment horizontal="center" vertical="center" wrapText="1"/>'
        '</xf>'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1">'
        '<alignment vertical="top" wrapText="1"/>'
        '</xf>'
        '</cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        '</styleSheet>'
    )


def core_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        '<dc:title>附录C角色表_友好能力实现跟踪</dc:title>'
        '<dc:creator>Codex CLI</dc:creator>'
        '<cp:lastModifiedBy>Codex CLI</cp:lastModifiedBy>'
        '</cp:coreProperties>'
    )


def app_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        '<Application>Microsoft Excel</Application>'
        '<TitlesOfParts><vt:vector size="1" baseType="lpstr"><vt:lpstr>角色表</vt:lpstr></vt:vector></TitlesOfParts>'
        '</Properties>'
    )


def export_workbook() -> Path:
    data = json.loads(DATA_PATH.read_text())
    rows = build_rows(data["characters"])
    widths = [14, 60, 10, 10, 12, 18, 42, 42, 42, 42, 10, 14, 14, 14, 14, 14, 14]

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(OUTPUT_PATH, "w", compression=ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml())
        zf.writestr("_rels/.rels", root_rels_xml())
        zf.writestr("xl/workbook.xml", workbook_xml())
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml())
        zf.writestr("xl/styles.xml", styles_xml())
        zf.writestr("docProps/core.xml", core_xml())
        zf.writestr("docProps/app.xml", app_xml())
        zf.writestr("xl/worksheets/sheet1.xml", worksheet_xml(rows, widths))
    return OUTPUT_PATH


if __name__ == "__main__":
    print(export_workbook())
