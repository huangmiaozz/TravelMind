# -*- coding: utf-8 -*-
"""Build the third-experiment requirements specification for TravelMind."""
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(r"D:\code\python\TravelMind")
ASSETS = ROOT / "docs" / "第三次实验_assets"
OUT = ROOT / "docs" / "第9组-TravelMind-需求规格说明书.docx"

CN_FONT = "宋体"
EN_FONT = "Times New Roman"
BODY_SIZE = 12
TABLE_HEADER_FILL = "D9E2F3"
TABLE_ALT_FILL = "F2F6FC"


# ---------------------------------------------------------------------------
# low-level helpers
# ---------------------------------------------------------------------------
def set_run_font(run, size=BODY_SIZE, bold=False, color=None):
    run.font.name = EN_FONT
    run.font.size = Pt(size)
    run.bold = bold
    if color:
        run.font.color.rgb = color
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), CN_FONT)
    rfonts.set(qn("w:ascii"), EN_FONT)
    rfonts.set(qn("w:hAnsi"), EN_FONT)


def shade(cell, fill):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tcPr.append(shd)


def set_cell_margins(cell, left=0.10, right=0.10, top=0.05, bottom=0.05):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = tcPr.find(qn("w:tcMar"))
    if tcMar is None:
        tcMar = OxmlElement("w:tcMar")
        tcPr.append(tcMar)
    for side, value in (("left", left), ("right", right), ("top", top), ("bottom", bottom)):
        el = tcMar.find(qn(f"w:{side}"))
        if el is None:
            el = OxmlElement(f"w:{side}")
            tcMar.append(el)
        el.set(qn("w:w"), str(int(value * 567)))
        el.set(qn("w:type"), "dxa")


def set_cell_text(cell, text, size=9, bold=False, center=False, color=None):
    cell.text = ""
    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER if center else WD_ALIGN_PARAGRAPH.LEFT
    pf = p.paragraph_format
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    pf.line_spacing = 1.0
    lines = str(text).split("\n")
    for i, line in enumerate(lines):
        run = p.add_run(line)
        set_run_font(run, size=size, bold=bold, color=color)
        if i < len(lines) - 1:
            run.add_break()
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER if center else WD_ALIGN_VERTICAL.TOP


def set_table_width(table, widths_cm):
    table.autofit = False
    table.allow_autofit = False
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    tblPr = table._tbl.tblPr
    tblW = tblPr.find(qn("w:tblW"))
    if tblW is None:
        tblW = OxmlElement("w:tblW")
        tblPr.append(tblW)
    tblW.set(qn("w:type"), "dxa")
    tblW.set(qn("w:w"), str(int(sum(widths_cm) * 567)))
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tblPr.append(layout)
    for row in table.rows:
        for idx, width in enumerate(widths_cm):
            row.cells[idx].width = Cm(width)
    for idx, width in enumerate(widths_cm):
        table.columns[idx].width = Cm(width)


def add_table(doc, headers, rows, widths, font_size=9, header_size=9,
              center_cols=None, alt=True):
    center_cols = center_cols or []
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    set_table_width(table, widths)
    hdr = table.rows[0]
    trPr = hdr._tr.get_or_add_trPr()
    tblHeader = OxmlElement("w:tblHeader")
    trPr.append(tblHeader)
    for idx, h in enumerate(headers):
        c = hdr.cells[idx]
        set_cell_text(c, h, size=header_size, bold=True, center=True)
        shade(c, TABLE_HEADER_FILL)
        set_cell_margins(c)
    for ridx, row in enumerate(rows):
        tr = table.add_row()
        trPr = tr._tr.get_or_add_trPr()
        cantSplit = OxmlElement("w:cantSplit")
        trPr.append(cantSplit)
        for cidx, value in enumerate(row):
            c = tr.cells[cidx]
            set_cell_text(c, value, size=font_size, center=(cidx in center_cols))
            set_cell_margins(c)
            if alt and ridx % 2 == 1:
                shade(c, TABLE_ALT_FILL)
    return table


def add_caption(doc, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pf = p.paragraph_format
    pf.space_before = Pt(6)
    pf.space_after = Pt(3)
    pf.keep_with_next = True
    run = p.add_run(text)
    set_run_font(run, size=10.5, bold=True)


def add_body(doc, text, indent=True):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    pf = p.paragraph_format
    pf.line_spacing = 1.5
    pf.space_before = Pt(0)
    pf.space_after = Pt(6)
    pf.first_line_indent = Pt(24) if indent else Pt(0)
    pf.keep_together = True
    run = p.add_run(text)
    set_run_font(run, size=BODY_SIZE)


def add_bullet(doc, text, size=BODY_SIZE):
    p = doc.add_paragraph(style="List Bullet")
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    pf = p.paragraph_format
    pf.line_spacing = 1.5
    pf.space_before = Pt(0)
    pf.space_after = Pt(3)
    pf.left_indent = Cm(0.74)
    pf.first_line_indent = Cm(-0.37)
    pf.keep_together = True
    run = p.add_run(text)
    set_run_font(run, size=size)


def add_ref(doc, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    pf = p.paragraph_format
    pf.line_spacing = 1.5
    pf.space_before = Pt(0)
    pf.space_after = Pt(3)
    pf.left_indent = Cm(0.74)
    pf.first_line_indent = Cm(-0.74)
    pf.keep_together = True
    run = p.add_run(text)
    set_run_font(run, size=BODY_SIZE)


def add_heading(doc, text, level=1):
    p = doc.add_heading(level=level)
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    pf = p.paragraph_format
    pf.keep_with_next = True
    if level == 1:
        pf.space_before = Pt(12)
        pf.space_after = Pt(6)
        size = 14
    elif level == 2:
        pf.space_before = Pt(10)
        pf.space_after = Pt(4)
        size = 13
    else:
        pf.space_before = Pt(8)
        pf.space_after = Pt(4)
        size = 12
    run = p.add_run(text)
    set_run_font(run, size=size, bold=True, color=RGBColor(0, 0, 0))


def add_picture(doc, path, width_cm=15.5):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.keep_with_next = True
    run = p.add_run()
    run.add_picture(str(path), width=Cm(width_cm))


def add_figure_caption(doc, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pf = p.paragraph_format
    pf.space_before = Pt(0)
    pf.space_after = Pt(8)
    run = p.add_run(text)
    set_run_font(run, size=10.5)


def add_page_number_footer(section):
    section.different_first_page_header_footer = True
    section.footer.is_linked_to_previous = False
    p = section.footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("第 ")
    set_run_font(run, size=9)
    fld1 = OxmlElement("w:fldChar")
    fld1.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    fld2 = OxmlElement("w:fldChar")
    fld2.set(qn("w:fldCharType"), "separate")
    t = OxmlElement("w:t")
    t.text = "1"
    fld3 = OxmlElement("w:fldChar")
    fld3.set(qn("w:fldCharType"), "end")
    run._r.append(fld1)
    run._r.append(instr)
    run._r.append(fld2)
    run._r.append(t)
    run._r.append(fld3)
    run2 = p.add_run(" 页")
    set_run_font(run2, size=9)


# ---------------------------------------------------------------------------
# document setup
# ---------------------------------------------------------------------------
doc = Document()
section = doc.sections[0]
section.page_width = Cm(21.0)
section.page_height = Cm(29.7)
section.left_margin = Cm(2.6)
section.right_margin = Cm(2.4)
section.top_margin = Cm(2.4)
section.bottom_margin = Cm(2.2)

styles = doc.styles
normal = styles["Normal"]
normal.font.name = EN_FONT
normal.font.size = Pt(BODY_SIZE)
normal._element.rPr.rFonts.set(qn("w:eastAsia"), CN_FONT)
normal.paragraph_format.line_spacing = 1.5
normal.paragraph_format.space_after = Pt(6)
normal.paragraph_format.first_line_indent = Pt(24)

for name, size in (("Heading 1", 14), ("Heading 2", 13), ("Heading 3", 12)):
    st = styles[name]
    st.font.name = EN_FONT
    st.font.size = Pt(size)
    st.font.bold = True
    st.font.color.rgb = RGBColor(0, 0, 0)
    rpr = st.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), CN_FONT)

add_page_number_footer(section)


# ---------------------------------------------------------------------------
# cover
# ---------------------------------------------------------------------------
def centered(text, size, bold=False, after=6, color=None):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pf = p.paragraph_format
    pf.space_before = Pt(0)
    pf.space_after = Pt(after)
    run = p.add_run(text)
    set_run_font(run, size=size, bold=bold, color=color)


centered("", 10, after=0)
centered("", 10, after=0)
centered("软件工程综合实验", 16, after=10)
centered("第三次实验：需求规格说明书", 14, after=24)
centered("TravelMind 智能旅行规划系统", 24, bold=True, after=8)
centered("需求规格说明书", 22, bold=True, after=24)
centered("本说明书用于定义系统需求与验收依据，不涉及界面布局、数据库表结构和算法实现。", 9, after=30)

cover = doc.add_table(rows=6, cols=2)
cover.style = "Table Grid"
cover.alignment = WD_TABLE_ALIGNMENT.CENTER
set_table_width(cover, [3.2, 7.0])
cover_rows = [
    ("小　　组", "第 9 组"),
    ("小组成员", "吴梓豪　杨诗哲　方伟明"),
    ("指导教师", "刘镭"),
    ("文档版本", "V1.1"),
    ("文档状态", "评审稿"),
    ("日　　期", "2026.11.13"),
]
for i, (k, v) in enumerate(cover_rows):
    c0, c1 = cover.rows[i].cells
    set_cell_text(c0, k, size=11, bold=True, center=True)
    set_cell_text(c1, v, size=11, center=True)
    set_cell_margins(c0, top=0.12, bottom=0.12)
    set_cell_margins(c1, top=0.12, bottom=0.12)
    # light borders
    for c in (c0, c1):
        tcPr = c._tc.get_or_add_tcPr()
        borders = OxmlElement("w:tcBorders")
        for edge in ("top", "left", "bottom", "right"):
            el = OxmlElement(f"w:{edge}")
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), "4")
            el.set(qn("w:color"), "BFBFBF")
            borders.append(el)
        tcPr.append(borders)

doc.add_page_break()

# ---------------------------------------------------------------------------
# pre-task division of labour (front matter, before section 1)
# ---------------------------------------------------------------------------
centered("实验三任务前小组分工", 16, bold=True, after=6)
centered("（2026 年 11 月 12 日）", 10.5, after=18)
add_body(doc, "在第三次实验任务开始前，小组先共同回顾《TravelMind 智能旅行规划系统可行性研究报告》和《项目开发计划书》，确认首版范围与功能边界；再按《需求规格说明书》模板搭好章节框架，然后按以下分工执笔。")
add_bullet(doc, "吴梓豪（组长）：负责引言、任务概述、数据流图（顶层图、0 层图及 1 层图）和需求评审与修订记录；负责全文统稿、格式调整与最终提交。")
add_bullet(doc, "杨诗哲：负责需求规定中的功能需求（3.1）、输入输出要求（3.3）和其他模型（5.3）；负责功能需求清单与验收要点的汇总。")
add_bullet(doc, "方伟明：负责性能要求（3.2）、数据管理能力（3.4）、故障处理（3.5）、其他专门要求（3.6）、运行环境规定（4）和数据字典（5.2）。")
add_body(doc, "任务执行中，三人先各自完成初稿，再进行交叉校对：吴梓豪核对功能需求、输入输出和用例是否与范围、数据流图一致；杨诗哲核对性能、数据、故障和运行环境条款是否与功能需求一致；方伟明核对术语、数据字典和格式。最后由吴梓豪统稿。")
add_body(doc, "以上分工在任务开始前经三人确认；执行中如需调整，由组长记录并在修订记录中说明。这次分工只针对第三次实验的《需求规格说明书》，第二次实验《项目开发计划书》的章节分工和开发 WBS 不变。")

doc.add_page_break()


# ---------------------------------------------------------------------------
# 1 引言
# ---------------------------------------------------------------------------
add_heading(doc, "1 引言", 1)
add_heading(doc, "1.1 编写目的", 2)
add_body(doc, "本需求规格说明书用于明确 TravelMind 智能旅行规划系统首版的功能需求、非功能需求、输入输出、运行环境和系统逻辑模型，作为后续概要设计、详细设计、编码、测试和课程验收的共同依据。主要读者包括第 9 组全体成员、指导教师刘镭、课程评审人以及后续接手开发的人员。")
add_body(doc, "本说明书只回答系统“做什么”，不描述界面布局、数据库表结构、算法步骤或代码实现；这些内容属于概要设计和详细设计阶段。文中功能、性能和数据指标均为首版验收目标，不代表系统已经实现。")

add_heading(doc, "1.2 项目背景", 2)
add_body(doc, "项目来源于软件工程综合实验可选课题库，课题登记名称为“旅游管理系统”，系统名称为 TravelMind。项目面向国内城市自由行：用户需要在多个平台之间反复搜集景点、开放时间、票价、路线和天气信息，再凭经验拼成行程；结果是静态文本，难以校验、比较和调整，也容易忽略闭馆、预约和步行超限等会让方案失效的因素。")
add_body(doc, "第一次实验的可行性研究结论为“有条件可行”，建议先完成单城市闭环；第二次实验将首版范围收敛为福州、北京两个验收城市，上海作为可选扩展。本说明书在此基础上定义单城市多日行程规划的需求，不扩展到跨城交通、订票支付、导航或旅行中的动态调整。")

add_heading(doc, "1.3 定义", 2)
add_caption(doc, "表 1  主要术语与缩写")
terms = [
    ("TravelMind", "本项目的智能旅行规划系统名称。"),
    ("POI", "Point of Interest，景点或地点。"),
    ("单城市多日", "一次行程只规划一个目的地城市内的连续多天旅行。"),
    ("硬约束", "开放时间、每日时间窗、每日最大步行距离等不可被偏好补偿的限制。"),
    ("软目标", "兴趣匹配、节奏、预算、路线便利、舒适度和天气适宜性等评分因素。"),
    ("数据状态", "已确认（confirmed）、估算（estimated）、未知（unknown）三态。"),
    ("静态顺序图", "按 1→2→3 顺序标注景点和相邻路段的静态地图，不提供导航。"),
    ("方案版本", "一次规划结果及其条件快照；改条件重新规划后生成新版本，旧版本保留。"),
    ("降级", "外部服务失败或数据缺失时，显式标注未知/估算，不伪装为真实数据。"),
    ("预算差额", "整单总预算减去已知总费用的差值；存在未知项时不能据此判定“未超预算”。"),
    ("高德 Web 服务", "提供 POI、路线、天气和静态地图的外部服务。"),
    ("GCJ-02", "高德地图使用的国测局坐标体系，与 WGS84（EPSG:4326）存在偏移。"),
]
add_table(doc, ["术语", "说明"], terms, [3.4, 12.2], font_size=9.5, center_cols=[0])

add_heading(doc, "1.4 参考资料", 2)
for text in [
    "（1）第 9 组.《TravelMind 智能旅行规划系统可行性研究报告》. 2026 年 10 月.",
    "（2）第 9 组.《TravelMind 智能旅行规划系统项目开发计划书》. 2026 年 10 月 30 日.",
    "（3）《软件工程综合实验——第三次实验任务说明》及课程实验指导书. 2026 年 11 月.",
    "（4）GB/T 9385—2008《计算机软件需求规格说明规范》.",
    "（5）GB/T 8567—2006《计算机软件文档编制规范》.",
    "（6）高德开放平台 Web 服务 API 文档：地点搜索、路径规划、天气查询、静态地图.",
    "（7）PostgreSQL 15 与 PostGIS 3 官方文档.",
]:
    add_ref(doc, text)


# ---------------------------------------------------------------------------
# 2 任务概述
# ---------------------------------------------------------------------------
add_heading(doc, "2 任务概述", 1)
add_heading(doc, "2.1 目标", 2)
add_body(doc, "系统面向单城市多日自由行，接收目的地城市、日期与天数、成人与儿童人数、整单预算、兴趣、节奏、交通偏好、每日可出行时间、每日最多景点数、每日最大步行距离以及餐饮/住宿预算，生成一份可执行、可解释、可保存的行程。行程包含每天景点顺序与时段、景点间真实路线、近 4 天天气、开放时间、费用估算、预算差额、数据来源和未知项；结果可保存为版本，改条件后重新生成。")
add_body(doc, "系统不以生成泛泛的攻略文章为目标，而是给出经过硬约束校验、并明确说明不确定性的计划；不建设订票、支付、库存、导航或跨城交通能力。")

add_heading(doc, "2.2 用户特点", 2)
add_caption(doc, "表 2  用户角色与特点")
users = [
    ("旅行者", "单用户/小团体，1～10 人", "能使用浏览器和表单", "出行前 1～3 次", "快速得到可执行行程，知道费用和未知项"),
    ("数据维护人员", "项目组 2～3 人", "熟悉表格或数据库工具", "每周 1～2 次", "维护 POI、票价、开放时间，记录来源"),
    ("指导教师/评审", "1～3 人", "熟悉软件工程", "阶段检查", "检查需求完整性、一致性和可验证性"),
]
add_table(doc, ["用户角色", "数量/范围", "业务水平", "使用频率", "主要诉求"], users,
          [2.4, 3.2, 3.2, 2.8, 4.4], font_size=9, center_cols=[0, 1, 2, 3])
add_body(doc, "首版不提供注册登录、权限管理和多租户。旅行者与数据维护人员通过不同使用方式区分，不作为系统角色权限；数据维护在受控环境中执行。")

add_heading(doc, "2.3 假定与约束", 2)
add_caption(doc, "表 3  开发与运行约束")
constraints = [
    ("周期与人力", "8 周课程周期，3 人，总投入约 288 人时。"),
    ("验收城市", "福州、北京；上海作为可选扩展，不纳入首版验收。"),
    ("景点数据", "每城 15～20 个 POI；每城 5 个重点景点核验官方票价与开放时间；其余标未知或估算。"),
    ("行程范围", "单城市多日，支持 1～5 天；首版生成 1 个方案，保存版本；不做跨城交通。"),
    ("外部服务", "高德 Web 服务提供 POI、路线、天气和静态地图；天气以实际返回的近 4 天为准。"),
    ("数据真实性", "官方数据人工核验；未知、失败、估算必须显式标注；不得用直线距离冒充真实路线。"),
    ("功能边界", "不做 AI 规划、订票/支付/库存、导航/交互地图、旅行中动态调整、固定多方案、第二天气源。"),
    ("运行约束", "浏览器访问；中文；人民币；Asia/Shanghai 时区；单用户 Demo；不做站内支付。"),
    ("验收场景", "福州、北京各至少 1 个 3 天行程；覆盖闭馆、路线失败、天气未知、票价未知、超预算和版本复现。"),
]
add_table(doc, ["类别", "约束内容"], constraints, [3.0, 12.6], font_size=9.5, center_cols=[0])
add_body(doc, "以上约束是需求边界。超出边界的请求应明确拒绝或标注“不支持”，不通过隐藏功能变相扩展；如课程要求变更，按修订记录更新本说明书。")


# ---------------------------------------------------------------------------
# 3 需求规定
# ---------------------------------------------------------------------------
add_heading(doc, "3 需求规定", 1)
add_heading(doc, "3.1 对功能的规定", 2)
add_body(doc, "首版功能需求共 22 项，编号 FR-01 至 FR-22。每项给出输入、处理、输出和验收要点；验收要点用于测试设计，不描述实现方式。FR-01～FR-20 面向旅行者，FR-21～FR-22 面向数据维护人员。")

add_caption(doc, "表 4  功能需求清单")
funcs = [
    ("FR-01", "城市选择", "输入：目的地城市。\n处理：只接受福州、北京；上海提示为可选扩展，不纳入首版验收。\n输出：确认城市或“暂不支持”。", "非法城市有明确提示；两城均可进入规划。"),
    ("FR-02", "日期与天数", "输入：起始日期、天数。\n处理：校验日期合法、天数 1～5 天、日期连续。\n输出：行程日期列表。", "非法日期/天数被拒绝；边界 1 天、5 天可用。"),
    ("FR-03", "人数", "输入：成人数、儿童数。\n处理：成人 1～10，儿童 0～10，总人数不超过 10。\n输出：人数与票种。", "0 人、负数、总人数超限被拒绝。"),
    ("FR-04", "预算与费用参数", "输入：整单总预算、餐饮人均日预算、住宿每间每晚预算、房间数、晚数。\n处理：非负校验；房间数≥1；晚数默认天数减 1，可覆盖。\n输出：费用参数。", "0 元、负数、超范围被拒绝；默认晚数正确。"),
    ("FR-05", "偏好与节奏", "输入：兴趣 0～100、节奏 0～100、交通偏好。\n处理：范围和枚举校验。\n输出：偏好快照。", "越界值被拒绝；四种交通偏好均可选。"),
    ("FR-06", "每日时间与限制", "输入：每日开始/结束时间、每日最多景点数、每日最大步行距离。\n处理：开始早于结束；景点数 1～8；步行 0～30 km。\n输出：每日约束。", "开始≥结束被拒绝；边界值可用。"),
    ("FR-07", "输入校验", "输入：全部用户输入。\n处理：字段级和跨字段校验，汇总错误。\n输出：错误列表或可提交状态。", "一次列出全部错误；错误定位到字段。"),
    ("FR-08", "候选景点检索", "输入：城市、日期、兴趣、预算。\n处理：读取城市 POI，按城市边界、开放日、兴趣和预算状态筛选候选。\n输出：候选集及数据状态。", "两城各返回 15～20 个候选；城外/重复 POI 不进入候选。"),
    ("FR-09", "开放时间与门票检查", "输入：候选 POI、行程日期。\n处理：已知闭馆或超出开放时间则淘汰；未知放行并标 unknown；记录票价状态。\n输出：可排候选及状态。", "已知闭馆不排；未知不误判为闭馆。"),
    ("FR-10", "多日行程编排", "输入：候选集、天数、每日约束。\n处理：把候选分配到各天，安排顺序和时段。\n输出：逐日行程草案。", "3 天行程可生成；跨日不重复 POI。"),
    ("FR-11", "硬约束校验", "输入：逐日行程草案。\n处理：检查开放时间、每日时间窗、每日景点上限、最大步行、跨日去重。\n输出：通过/违规/未知及原因。", "每类硬约束有独立用例；违规不靠评分补偿。"),
    ("FR-12", "路线获取", "输入：相邻景点、交通偏好。\n处理：调用高德路线，记录方式、距离、耗时、费用和状态；失败标 failed。\n输出：路线段。", "路线失败不填直线距离；费用/耗时为空。"),
    ("FR-13", "天气获取与影响", "输入：城市、行程日期。\n处理：取近 4 天预报；超出/失败标 unknown；天气影响户外/室内评分。\n输出：每日天气及说明。", "超出 4 天标未知；未知按中性处理。"),
    ("FR-14", "费用核算", "输入：门票、路线、人数、餐饮/住宿参数。\n处理：计算门票、市内交通、餐饮、住宿四类费用；保留 confirmed/estimated/unknown；汇总已知总额和预算差额。\n输出：费用明细。", "未知费用不按 0 计；预算差额和未知项同时展示。"),
    ("FR-15", "结果展示", "输入：完整方案。\n处理：按日组织景点、时间、路线、天气、费用、来源和未知项。\n输出：结果内容。", "每日信息完整；来源/状态可见。"),
    ("FR-16", "静态顺序图", "输入：每日有序景点。\n处理：生成带 1→2→3 编号和相邻路段的静态图；失败返回有序列表。\n输出：图片或列表及状态。", "顺序与行程一致；失败不阻塞方案。"),
    ("FR-17", "未知与失败标注", "输入：所有外部服务和数据项。\n处理：统一记录 status、source、reason；未知项单列。\n输出：状态标签和说明。", "unknown 不显示为 0/成功；失败有原因。"),
    ("FR-18", "方案保存", "输入：条件快照和规划结果。\n处理：保存方案、版本号、生成时间。\n输出：版本 ID。", "保存后重载内容一致；版本号唯一。"),
    ("FR-19", "版本查看与重新生成", "输入：历史方案、修改后的条件。\n处理：列出/查看旧版本；重新生成新版本，旧版本保留。\n输出：版本列表或新版本。", "旧版本不被覆盖；新版本条件可追溯。"),
    ("FR-20", "空/部分结果", "输入：无可行或部分可行的行程。\n处理：返回空/部分状态、原因和可调整项。\n输出：结果状态与说明。", "不返回 500；不硬凑行程。"),
    ("FR-21", "城市与 POI 数据维护", "输入：城市、POI、坐标、票价、开放时间、来源、状态、核验时间。\n处理：校验完整性、城市边界、重复点和异常坐标；记录来源。\n输出：更新结果或待确认清单。", "城外/重复/异常坐标可发现；来源可追溯。"),
    ("FR-22", "重点景点核验", "输入：每城 5 个重点景点。\n处理：记录官方票价、开放时间、预约要求、来源和核验日期。\n输出：核验记录。", "5×2 条记录完整；冲突时官方优先。"),
]
add_table(doc, ["编号", "功能名称", "需求描述（输入—处理—输出）", "验收要点"], funcs,
          [1.9, 2.5, 7.95, 3.65], font_size=8.5, header_size=9, center_cols=[0, 1])

add_heading(doc, "3.1.1 功能边界", 3)
add_body(doc, "以下功能不在首版范围：AI 规划或对话修改、跨城交通与航班/火车、站内订票/支付/退改/库存、导航与交互式 JS 地图、全国城市覆盖与通用爬虫、旅行中动态局部调整、固定多方案优化、第二天气源、用户注册登录。若后续增加，须按变更流程更新本说明书，不把未列入范围的功能作为验收内容。")

add_heading(doc, "3.2 对性能的规定", 2)
add_body(doc, "性能指标以课程演示环境为基准，外部服务延迟不可控时按降级要求处理；以下指标应可量化、可检验。")
add_caption(doc, "表 5  性能与容量指标")
perf = [
    ("输入校验响应", "95% 请求 ≤1 s；错误一次性返回", "100 次表单校验，统计 P95"),
    ("规划响应", "3 天、20 个 POI、正常网络下 P95 ≤8 s，最大 ≤15 s", "固定数据 + 真实接口冒烟"),
    ("静态图响应", "单日图 ≤3 s；失败降级 ≤1 s", "逐日生成，记录耗时"),
    ("页面首屏", "10 Mbps 网络下 ≤3 s", "Chrome/Edge 实测 3 次"),
    ("并发能力", "5 个规划请求、20 个结果页访问可正常响应；超出排队或提示", "并发脚本/手工压测"),
    ("数据容量", "2 城、30～40 个 POI、200 个版本、单方案 5 天×8 项", "种子数据 + 容量检查"),
    ("精度", "距离 1 m、时间 1 min、金额 1 元、坐标 6 位小数", "抽样对比"),
    ("可用与恢复", "演示时段可用性 ≥95%；RPO ≤24 h、RTO ≤4 h", "备份恢复演练"),
]
add_table(doc, ["指标", "要求", "验证方法"], perf, [3.0, 8.6, 4.0], font_size=9, center_cols=[0])

doc.add_page_break()
add_heading(doc, "3.3 输入输出要求", 2)
add_caption(doc, "表 6  主要输入")
inputs = [
    ("城市", "用户", "枚举", "福州/北京；上海可选", "只接受已支持城市"),
    ("起始日期", "用户", "日期", "YYYY-MM-DD，不早于当天", "合法日期"),
    ("天数", "用户", "整数", "1～5 天", "范围校验"),
    ("成人/儿童", "用户", "整数", "成人 1～10；儿童 0～10；总数 ≤10", "范围与总数校验"),
    ("整单总预算", "用户", "数值", "0～100000 元", "非负"),
    ("兴趣/节奏", "用户", "整数", "0～100", "范围校验"),
    ("交通偏好", "用户", "枚举", "步行/公交/驾车/混合", "枚举校验"),
    ("每日开始/结束", "用户", "时间", "HH:MM，开始早于结束", "时间窗校验"),
    ("每日最多景点", "用户", "整数", "1～8", "范围校验"),
    ("每日最大步行", "用户", "数值", "0～30 km", "非负"),
    ("餐饮人均日预算", "用户", "数值", "0～1000 元", "非负"),
    ("住宿每间每晚", "用户", "数值", "0～5000 元", "非负"),
    ("房间数/晚数", "用户", "整数", "房间 1～5；晚数 0～14，默认天数减 1", "范围校验"),
    ("数据维护输入", "数据维护", "文本/数值/日期", "城市、POI、票价、开放时间、来源、状态、核验时间", "必填与来源校验"),
]
add_table(doc, ["输入项", "来源", "格式", "范围/取值", "校验要求"], inputs,
          [3.0, 1.8, 2.4, 5.2, 3.2], font_size=8.8, center_cols=[0, 1, 2])

add_caption(doc, "表 7  主要输出")
outputs = [
    ("行程方案", "逐日景点、时间、路线、天气、费用、来源、未知项", "结构化结果 + 页面", "旅行者"),
    ("每日行程", "日期、景点顺序、起止时间、步行距离", "逐日列表", "旅行者"),
    ("路线段", "方式、距离、耗时、费用、状态", "结构化字段", "旅行者"),
    ("天气", "日期、天气、温度、适宜性、状态", "逐日信息", "旅行者"),
    ("费用明细", "门票、市内交通、餐饮、住宿及状态", "分类汇总", "旅行者"),
    ("预算差额", "总预算－已知总费用；未知项数量", "数值 + 说明", "旅行者"),
    ("未知项", "数据项、原因、影响范围", "清单", "旅行者"),
    ("静态图", "每日 1→2→3 顺序图或失败状态", "图片/列表", "旅行者"),
    ("方案版本", "版本号、条件快照、生成时间", "版本记录", "旅行者"),
    ("错误/部分状态", "字段错误、空/部分结果及原因", "状态 + 说明", "旅行者/评审"),
]
add_table(doc, ["输出项", "内容", "形式", "接收对象"], outputs,
          [3.0, 7.2, 3.2, 2.6], font_size=9, center_cols=[0, 2, 3])
add_body(doc, "输入不合法时返回字段级错误；城市不支持或无 POI 时给出明确提示；排不出行程时返回空/部分状态和原因；外部服务失败时返回 unknown/failed，不返回伪造数据；数据库不可用时返回可重试提示，不写入半成品。")

add_heading(doc, "3.4 数据管理能力要求", 2)
add_caption(doc, "表 8  数据规模与增长")
data_scale = [
    ("城市", "2 个", "每学期最多增加 1 个", "名称、编码、边界、状态"),
    ("POI", "30～40 个", "每增加 1 城约增加 20 个", "坐标、类型、来源、状态、核验时间"),
    ("重点核验记录", "10 条（5×2）", "每增加 1 城增加 5 条", "官方票价、开放时间、预约要求、来源"),
    ("方案版本", "200 个", "约 50 个/月", "条件快照、结果、费用、生成时间"),
    ("行程项", "单方案 5 天×8 项", "随方案增长", "时间、路线、费用、状态"),
    ("外部数据缓存", "1000 条", "按 TTL 清理", "路线、天气、静态图；不作为事实来源"),
]
add_table(doc, ["数据对象", "首版规模", "增长假设", "管理要求"], data_scale,
          [3.0, 3.4, 4.2, 5.4], font_size=9, center_cols=[0, 1, 2])
add_body(doc, "数据存储采用关系型数据库，方案结果以快照形式保存；具体表结构不在本说明书展开。演示环境每日备份，保留 7 天；恢复目标 RPO≤24 h、RTO≤4 h。")
add_body(doc, "数据维护记录来源、采集时间、核验时间、状态和原始文本；超过 180 天未复核的重点数据标“待复核”。数据冲突时官方来源优先，保留冲突记录，不静默覆盖。数据规模不大，但要求可追溯，不能把估算或未知写成确定值。")

add_heading(doc, "3.5 故障处理要求", 2)
add_caption(doc, "表 9  故障与降级处理")
failures = [
    ("高德超时/5xx/配额不足", "有限重试后标 failed/unknown；核心方案仍可查看", "说明哪一段路线/天气未获取", "不把失败当成功；记录状态"),
    ("路线失败", "distance/duration 为空；不填直线距离", "该路段“路线待确认”", "允许部分结果；不声称步行约束通过"),
    ("天气超出 4 天/失败", "weather.status=unknown；按中性评分", "“暂无可靠预报”", "不猜测；不声称已按天气优化"),
    ("静态图失败", "map.status=failed；返回有序列表", "“地图暂不可用，按列表查看顺序”", "不阻塞方案"),
    ("无可排行程", "返回 partial/empty + 原因", "“当前条件下排不出，可调整预算/步行/天数”", "不硬凑；不返回 500"),
    ("输入非法", "字段级错误，汇总返回", "指出字段和取值范围", "不发起规划请求"),
    ("数据库不可用", "事务回滚，返回可重试提示", "“保存失败，请稍后重试”", "不写入半成品"),
    ("数据冲突", "官方优先；保留冲突记录", "显示来源和核验时间", "不静默覆盖"),
    ("Key 泄露/日志异常", "立即轮换 Key；停止输出敏感日志", "不向用户暴露密钥", "保留审计记录"),
    ("浏览器刷新/重复提交", "已保存版本可重新加载；重复提交不产生重复版本", "提示“已保存/正在处理”", "版本号唯一"),
]
add_table(doc, ["故障场景", "系统响应", "用户提示", "恢复要求"], failures,
          [3.6, 6.0, 3.6, 3.4], font_size=8.8, center_cols=[0])
add_body(doc, "任何降级都不能伪装成成功；失败结果仍可查看，但必须标明影响范围。涉及费用、路线、天气和开放时间的未知项，应按 3.6.7 的数据准确性要求保留来源和状态。")

add_heading(doc, "3.6 其他专门要求", 2)
add_heading(doc, "3.6.1 安全性", 3)
add_bullet(doc, "高德 Key 只存放在后端环境配置中，不进入前端、日志、截图或提交仓库；部署时使用 HTTPS。")
add_bullet(doc, "所有用户输入进行类型、范围和跨字段校验；数据库访问使用参数化查询，避免注入。")
add_bullet(doc, "首版不收集账号、支付和个人身份信息；只保存行程条件和结果，不保存敏感个人信息。")
add_bullet(doc, "接口错误不返回堆栈和密钥；对外错误信息只说明原因和可操作建议。")

add_heading(doc, "3.6.2 易用性", 3)
add_bullet(doc, "全中文界面，金额、距离、时间均带单位；错误提示定位到具体字段，并给出合法范围。")
add_bullet(doc, "首次使用者应在 3 分钟内完成一次 3 天行程输入；主要操作不超过 3 个步骤。")
add_bullet(doc, "confirmed/estimated/unknown 使用统一标签和颜色；未知项不隐藏在折叠内容中。")

add_heading(doc, "3.6.3 可靠性", 3)
add_bullet(doc, "外部服务失败时核心结果仍可查看；路线、天气、静态图可分别降级，不因一个失败导致整单不可用。")
add_bullet(doc, "方案保存采用事务；保存失败不产生半成品；旧版本不被新版本覆盖。")
add_bullet(doc, "演示环境每日备份，保留 7 天；每学期至少做一次恢复演练。")

add_heading(doc, "3.6.4 可维护性", 3)
add_bullet(doc, "功能按输入校验、候选检索、行程编排、路线/天气/费用、结果展示、版本管理划分，模块边界清晰。")
add_bullet(doc, "评分权重、每日上限、天气窗口等参数可配置；变更不需要改多处代码。")
add_bullet(doc, "关键操作记录请求标识、外部调用状态和耗时；日志不包含 Key 和个人信息。")

add_heading(doc, "3.6.5 可移植性", 3)
add_bullet(doc, "客户端支持 Chrome/Edge 最近两个主要版本；不依赖特定操作系统。")
add_bullet(doc, "服务端支持 Windows 或 Linux；数据库使用 PostgreSQL/PostGIS；外部地图服务通过适配层隔离。")
add_bullet(doc, "不绑定云厂商；演示可使用本地或校内服务器。")

add_heading(doc, "3.6.6 合规性", 3)
add_bullet(doc, "遵守高德开放平台条款，保留 attribution；不批量抓取、不转售数据。")
add_bullet(doc, "官方票价、开放时间和预约规则以人工核验记录为准；不抓取禁止采集的站点。")
add_bullet(doc, "课程 Demo 非商业用途；不提供订票、支付、退改或库存承诺。")

add_heading(doc, "3.6.7 数据准确性", 3)
add_bullet(doc, "每条 POI、票价、开放时间、路线、天气和费用记录都带 source、status、verified_at（适用时）。")
add_bullet(doc, "每城只对 5 个重点景点做官方核验；其余标未知或估算，不冒充官方实时数据。")
add_bullet(doc, "未知费用不计入已知总额，未知项单列；预算差额在存在未知项时标注“待确认”。")


# ---------------------------------------------------------------------------
# 4 运行环境规定
# ---------------------------------------------------------------------------
add_heading(doc, "4 运行环境规定", 1)
add_heading(doc, "4.1 设备", 2)
add_caption(doc, "表 10  设备与网络")
devices = [
    ("客户端", "i5 及以上、8 GB 内存、1366×768 及以上分辨率", "Chrome/Edge 浏览器；10 Mbps 网络"),
    ("服务器", "4 核 8 GB、100 GB 数据盘；可选云服务器或校内服务器", "演示与试运行"),
    ("备份", "100 GB 可用空间", "每日数据库备份，保留 7 天"),
    ("网络", "HTTPS 443；稳定公网或校内网络", "访问高德服务与演示系统"),
]
add_table(doc, ["设备", "最低配置", "用途/说明"], devices, [3.4, 8.0, 4.2], font_size=9, center_cols=[0])

add_heading(doc, "4.2 支持软件", 2)
add_caption(doc, "表 11  支持软件")
software = [
    ("操作系统", "Windows 11/10；Linux（部署可选）", "开发与运行"),
    ("浏览器", "Chrome/Edge 最近两个主要版本", "用户访问"),
    ("数据库", "PostgreSQL 15+，启用 PostGIS 3.x", "关系与空间数据"),
    ("运行时", "Python 3.11；Node.js 20（仅前端构建）", "后端运行与前端构建"),
    ("Web 服务器", "Nginx（可选）", "静态资源与反向代理"),
    ("外部服务", "高德 Web 服务 Key（POI/路线/天气/静态图）", "真实路线、天气与地图"),
    ("工具", "Git、VS Code/PyCharm、pgAdmin/DBeaver", "开发、版本管理与数据维护"),
]
add_table(doc, ["类别", "名称/版本", "用途"], software, [3.4, 8.4, 3.8], font_size=9, center_cols=[0])

add_heading(doc, "4.3 接口", 2)
add_caption(doc, "表 12  接口需求")
interfaces = [
    ("用户界面", "旅行者", "表单输入、行程结果、费用、未知项", "HTTPS/HTML", "按需"),
    ("高德 POI", "高德 Web 服务", "地点搜索、城市编码、POI 坐标", "HTTPS/JSON", "规划前/数据维护"),
    ("高德路线", "高德 Web 服务", "步行/公交/驾车/骑行距离、耗时、费用", "HTTPS/JSON", "相邻景点对"),
    ("高德天气", "高德 Web 服务", "近 4 天预报", "HTTPS/JSON", "按城市/日期"),
    ("高德静态图", "高德 Web 服务", "每日 1→2→3 顺序图", "HTTPS/图片", "按日"),
    ("官方数据", "数据维护人员", "票价、开放时间、预约要求、来源", "受控录入/导入", "每周/演示前"),
    ("数据库", "系统内部", "城市、POI、方案、版本、缓存", "SQL/内网", "按请求"),
    ("硬件", "运行设备", "网络、显示、键盘鼠标", "系统调用", "持续"),
]
add_table(doc, ["接口", "对方", "内容", "协议/形式", "频率"], interfaces,
          [2.8, 3.4, 4.8, 3.0, 2.0], font_size=8.8, center_cols=[0, 3, 4])
add_body(doc, "外部接口返回的数据必须带来源和状态；路线、天气、静态图失败按 3.5 处理。接口字段的具体格式在概要设计中细化，本说明书只规定接口内容和质量要求。")

add_heading(doc, "4.4 控制", 2)
add_body(doc, "系统通过浏览器访问，首版单用户、不做注册登录；数据维护由项目组在受控环境中执行，不向普通用户开放。规划操作按需发起，演示期预计每天 1～10 次，峰值按 5 个并发规划请求设计。")
add_body(doc, "系统的启动、停止、备份和 Key 轮换由部署管理员控制；外部服务配额由项目组在演示前检查。系统不提供用户级支付、订票或库存控制。")


# ---------------------------------------------------------------------------
# 5 系统逻辑模型
# ---------------------------------------------------------------------------
add_heading(doc, "5 系统逻辑模型", 1)
add_heading(doc, "5.1 数据流图", 2)
add_body(doc, "本节采用结构化分析方法，用数据流图描述系统的数据处理过程。图中矩形表示外部实体，圆角矩形表示处理，开口矩形表示数据存储，箭头表示数据流；数据流编号与 5.2 节数据字典对应。")

add_heading(doc, "5.1.1 顶层数据流图", 3)
add_picture(doc, ASSETS / "dfd_context.png", 15.5)
add_figure_caption(doc, "图 5-1  系统顶层数据流图")
add_body(doc, "顶层图把系统视为处理 P0。旅行者输入出行条件与偏好，系统输出行程方案、费用、天气和版本；系统向高德 Web 服务请求 POI、路线、天气和静态图，并接收结果/状态；官方数据/人工维护提供票价和开放时间核验记录。")

add_heading(doc, "5.1.2 0 层数据流图", 3)
add_picture(doc, ASSETS / "dfd_level0.png", 15.8)
add_figure_caption(doc, "图 5-2  系统 0 层数据流图")
add_body(doc, "0 层图把系统分解为六个处理：P1 需求录入与校验、P2 候选景点检索与筛选、P3 多日行程编排、P4 路线/天气/费用计算、P5 结果展示与静态图、P6 方案保存与版本管理。D1 保存城市、POI、票价和开放时间；D2 保存方案与版本；D3 缓存外部路线、天气和静态图结果。")
add_body(doc, "P4 与高德服务交互，获得真实路线和天气；P5 向旅行者输出行程、费用、未知项和静态图；P6 保存条件快照与结果，D2 向 P5 提供历史版本。")

add_heading(doc, "5.1.3 1 层数据流图（P3 分解）", 3)
add_picture(doc, ASSETS / "dfd_level1.png", 15.8)
add_figure_caption(doc, "图 5-3  P3 多日行程编排的 1 层数据流图")
add_body(doc, "P3 分解为 P3.1 候选池整理、P3.2 逐日分配、P3.3 日内顺序与时间安排、P3.4 硬约束校验、P3.5 调整/裁剪。P3.4 发现违规或未知项时交给 P3.5，P3.5 将调整结果反馈给 P3.2；可行或部分可行的行程交给 P4 计算路线、天气和费用。")

add_heading(doc, "5.2 数据字典", 2)
add_body(doc, "数据字典对数据流图中的主要数据流、数据存储和数据项进行定义；字段的最终类型和长度在概要设计中细化。")

add_caption(doc, "表 13  主要数据流")
flows = [
    ("F1", "出行条件", "旅行者 → P1", "城市、日期、天数、人数、预算、兴趣、节奏、交通偏好、时间窗、步行上限"),
    ("F2", "已校验条件", "P1 → P2", "通过校验的出行条件与偏好快照"),
    ("F3", "候选景点集", "P2 → P3", "POI 编号、名称、坐标、开放状态、票价状态、兴趣标签"),
    ("F4", "初步逐日行程", "P3 → P4", "日期、景点顺序、预计时段、步行距离"),
    ("F5", "路线/天气结果", "高德 → P4", "距离、耗时、费用、天气、状态、来源"),
    ("F6", "完整方案", "P4 → P5", "逐日行程、路线段、天气、费用、预算差额、未知项"),
    ("F7", "行程结果", "P5 → 旅行者", "行程、静态图、费用、未知项、版本号"),
    ("F8", "待保存方案", "P5 → P6", "条件快照 + 规划结果"),
    ("F9", "版本记录", "P6 → D2", "版本号、条件、结果、生成时间"),
    ("F10", "历史版本", "D2 → P5", "版本列表、历史结果、条件"),
    ("F11", "核验记录", "官方数据 → D1/P3", "票价、开放时间、预约要求、来源、核验日期"),
    ("F12", "缓存数据", "P4 ↔ D3", "路线、天气、静态图结果及 TTL"),
]
add_table(doc, ["编号", "数据流", "来源 → 去向", "主要内容"], flows,
          [1.8, 2.5, 4.5, 7.2], font_size=8.8, center_cols=[0, 1, 2])

add_caption(doc, "表 14  数据存储")
stores = [
    ("D1", "城市/POI/票价/开放时间", "城市编码、POI 坐标、类型、室内外属性、开放时间、票价、来源、状态、核验时间", "P2/P3 读取；数据维护更新"),
    ("D2", "方案/版本", "条件快照、逐日行程、费用、未知项、版本号、生成时间", "P5/P6 读写；历史版本查询"),
    ("D3", "外部数据缓存", "路线、天气、静态图响应、请求键、TTL、状态", "P4 读写；减少重复调用"),
]
add_table(doc, ["编号", "名称", "主要内容", "使用说明"], stores,
          [1.7, 3.2, 7.5, 3.6], font_size=9, center_cols=[0, 1])

add_caption(doc, "表 15  主要数据项")
items = [
    ("城市编码", "字符串", "福州/北京（上海可选）", "城市唯一标识"),
    ("城市名称", "字符串", "2～10 个汉字", "展示名称"),
    ("POI 编号", "字符串", "全局唯一", "景点唯一标识"),
    ("POI 名称", "字符串", "1～50 个字符", "景点名称"),
    ("经纬度", "数值", "中国范围；6 位小数", "GCJ-02 或转换后的 WGS84，需标坐标系"),
    ("室内外属性", "枚举", "indoor/outdoor/unknown", "天气评分使用"),
    ("开放时间", "字符串/区间", "周几 + 时段 + 状态", "硬约束；未知放行并标注"),
    ("票价", "数值 + 状态", "0～9999 元；confirmed/estimated/unknown", "未知不得按 0 计"),
    ("来源/核验时间", "字符串/日期", "URL/说明 + 日期", "数据可追溯"),
    ("起始日期", "日期", "YYYY-MM-DD", "行程第一天"),
    ("天数", "整数", "1～5", "连续行程天数"),
    ("成人数/儿童数", "整数", "成人 1～10；儿童 0～10", "人数与票种"),
    ("整单总预算", "数值", "0～100000 元", "所有同行人员合计"),
    ("兴趣/节奏", "整数", "0～100", "偏好强度"),
    ("交通偏好", "枚举", "步行/公交/驾车/混合", "路线方式"),
    ("每日时间窗", "时间", "HH:MM～HH:MM", "硬约束"),
    ("每日最多景点/最大步行", "整数/数值", "1～8 个；0～30 km", "硬约束"),
    ("餐饮/住宿预算", "数值", "餐饮 0～1000 元/人/日；住宿 0～5000 元/间/晚", "费用估算"),
    ("行程日/行程项", "结构化", "日期 + 景点顺序 + 起止时间", "每日安排"),
    ("路线段", "结构化", "方式、距离、耗时、费用、状态", "相邻景点之间"),
    ("费用项", "结构化", "类别、金额、状态、说明", "四类费用"),
    ("方案版本", "结构化", "版本号、条件快照、结果、生成时间", "可追溯"),
    ("未知项", "结构化", "数据项、原因、影响范围", "不得隐藏"),
]
add_table(doc, ["数据项", "类型", "取值范围/格式", "说明"], items,
          [3.4, 3.0, 5.6, 4.0], font_size=8.6, center_cols=[0, 1])

add_heading(doc, "5.3 其他模型", 2)
add_body(doc, "本节用用例概述补充说明系统与外部参与者的交互；用例图、E-R 图和状态转换图不在此展开，必要时在概要设计阶段补充。")
add_caption(doc, "表 16  用例概述")
usecases = [
    ("旅行者", "录入出行条件", "输入城市、日期、人数、预算、偏好和限制"),
    ("旅行者", "查看行程", "查看逐日景点、路线、天气、费用、来源和未知项"),
    ("旅行者", "保存方案", "保存条件快照和结果，形成版本"),
    ("旅行者", "查看历史版本", "查看旧版本并比较条件/结果"),
    ("旅行者", "重新生成", "修改条件后生成新版本，旧版本保留"),
    ("数据维护人员", "维护城市/POI", "录入或更新城市、POI、票价、开放时间、来源"),
    ("数据维护人员", "核验重点景点", "每城 5 个重点景点的官方票价、开放时间、预约要求"),
    ("高德 Web 服务", "提供外部数据", "POI、路线、天气、静态图及状态"),
]
add_table(doc, ["参与者", "用例", "说明"], usecases, [3.4, 4.2, 8.4], font_size=9, center_cols=[0, 1])


# ---------------------------------------------------------------------------
# 6 需求评审与修订记录
# ---------------------------------------------------------------------------
add_heading(doc, "6 需求评审与修订记录", 1)
add_heading(doc, "6.1 评审记录", 2)
add_body(doc, "小组于 2026 年 11 月 12 日对需求规格说明书初稿进行组内评审，逐项检查功能需求是否覆盖项目计划范围、表述是否可验证、各章节和 DFD 是否一致。")
add_caption(doc, "表 17  评审信息")
review_info = [
    ("评审时间", "2026 年 11 月 12 日 15:00—16:30"),
    ("评审地点", "线上会议"),
    ("参加人员", "吴梓豪、杨诗哲、方伟明"),
    ("主持人", "吴梓豪"),
    ("记录人", "方伟明"),
    ("评审材料", "需求规格说明书初稿、项目开发计划书、DFD 初稿"),
]
add_table(doc, ["项目", "内容"], review_info, [3.4, 12.2], font_size=9.5, center_cols=[0])

add_caption(doc, "表 18  评审问题与修改")
issues = [
    ("1", "功能清单缺少“城市切换”和“版本重新生成”的验收口径", "补充 FR-01、FR-19 的输入、输出和验收要点", "吴梓豪"),
    ("2", "未知费用、路线失败的描述不够明确", "补充 FR-17 和 3.5 的降级要求，明确未知不按 0 计", "杨诗哲"),
    ("3", "0 层图中 P5 与 P6 的边界不够清楚", "调整数据流：P5 输出结果并提交保存，P6 只负责版本写入与历史读取", "方伟明"),
    ("4", "性能指标“响应快”不可验证", "改为 P95、最大时长、并发数和数据容量等量化指标", "杨诗哲"),
    ("5", "运行环境写了实现框架，容易越界", "改为操作系统、浏览器、数据库、运行时等环境要求，不写框架和代码", "吴梓豪"),
]
add_table(doc, ["序号", "发现的问题", "修改情况", "负责人"], issues,
          [1.7, 6.0, 6.3, 2.0], font_size=9, center_cols=[0, 3])
add_body(doc, "评审结论：功能需求覆盖项目计划书确定的首版范围，硬约束、未知处理和版本要求可验证；按上述意见修改后形成 V1.1，提交指导教师评审。")

add_heading(doc, "6.2 修订记录", 2)
add_caption(doc, "表 19  修订记录")
revisions = [
    ("V1.0", "2026-11-13", "初稿：完成引言、任务概述、需求规定、运行环境、DFD、数据字典和评审记录", "第 9 组"),
    ("V1.1", "2026-11-13", "根据组内评审意见补充功能边界、量化性能指标、调整 0 层图数据流、修正运行环境表述", "吴梓豪"),
]
add_table(doc, ["版本号", "修订日期", "修订内容", "修订人"], revisions,
          [2.0, 2.8, 9.6, 2.6], font_size=9, center_cols=[0, 1, 3])

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_before = Pt(24)
run = p.add_run("—— 本说明书完 ——")
set_run_font(run, size=10.5)


# ---------------------------------------------------------------------------
# metadata + save
# ---------------------------------------------------------------------------
cp = doc.core_properties
cp.title = "TravelMind 智能旅行规划系统需求规格说明书"
cp.author = "第 9 组"
cp.subject = "软件工程综合实验第三次实验"
cp.comments = "需求规格说明书 V1.1"

OUT.parent.mkdir(parents=True, exist_ok=True)
doc.save(str(OUT))
print(OUT)
