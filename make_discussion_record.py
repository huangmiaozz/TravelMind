# -*- coding: utf-8 -*-
"""Create a group-discussion record in the same visual format as the provided sample."""
from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Pt
from docx.text.paragraph import Paragraph

SAMPLE = Path(r"C:\Users\aaa\Downloads\第九小组小组讨论.docx")
OUT = Path(r"D:\code\python\TravelMind\docs\第二次实验_第9组_TravelMind小组讨论记录.docx")

TITLE = "小组讨论过程"

PARAGRAPHS = [
    "2026年10月28日晚上，我们小组三个人围绕第二次实验的项目开发计划开了个短会，方伟明记录。吴梓豪先把任务讲清楚：这次不是再写可行性研究，而是要把八周怎么开发、怎么分工、怎么排进度、有哪些风险写成能执行的计划。我们回顾了第一次实验“有条件可行”的结论，决定先把范围收住。",
    "讨论范围时，杨诗哲想多放几个城市、功能做全一点；方伟明担心数据和接口吃不消；吴梓豪主张先做单城市多日、保证主流程闭环。最后定下首版只做福州和北京，上海作为可选扩展，不纳入验收；每城15到20个POI，其中5个重点景点核验官方票价和开放时间，其余标未知或估算。",
    "功能上也争了一会儿。有人提AI规划、跨城交通、订票支付、多方案对比，大家觉得八周内做不完，决定首版只做单城市多日、1个方案加版本保存、每天1→2→3静态顺序图，费用只算门票、市内交通、餐饮、住宿四类；AI、跨城、订票、导航、动态调整、固定多方案和第二天气源都不做。",
    "数据这块方伟明最担心，票价和开放时间不一定都能从官方拿到，高德有些字段也不完整。吴梓豪说要把状态分清楚：已核验标已确认，估算标估算，拿不到标未知，不能把未知写成0。天气只有近4天预报，超出就标未知、按中性评分；路线失败就标失败，不能拿直线距离冒充真实路线。",
    "技术方案也过了一遍。后端打算用FastAPI，前端Vue 3加TypeScript，数据库PostgreSQL，空间查询用PostGIS。方伟明问15到20个POI用PostGIS是不是太重；吴梓豪说它不算真实路线，只做入库校验、去重、候选筛选和区域聚类，真实距离和时间还是走高德，部署麻烦可以退化成经纬度加边界框。",
    "进度是讨论最久的。八周要完成需求契约、数据接入、规划器、前后端闭环、回归和验收，大家都觉得紧。我们按S1到S6排了一遍，里程碑定M1到M5，第7周回归缓冲，第8周试用验收；如果延期，先砍Three.js、静态图这类可选内容，再缩POI数量，不能砍核心闭环。",
    "分工也重新对了。开发上吴梓豪168人时、杨诗哲72、方伟明48，合计288。杨诗哲觉得168太高，方伟明觉得48太少；吴梓豪说288是按3人8周平均12小时算的总量，168是角色加权，不是每周固定21小时，还包括契约、联调、评审这些不好拆的工作。大家同意M2、M3检查工时，超了就把4.3路线段或5.3静态图转出去。",
    "报告撰写也分了工：吴梓豪写引言、软件作用范围、开发模型并统稿；杨诗哲写资源估算、进度计划、WBS；方伟明写风险、支持性计划和修订记录。初稿后交叉校对，吴看范围、进度、WBS是否一致，杨核对工时、预算和进度数字，方检查术语、格式和参考文献。",
    "风险列了官方数据缺失、高德配额或失败、天气只有4天、范围蔓延、联调延期几条，对应办法是重点景点只核验5个、其余标未知，路线天气做缓存和降级，新增功能走变更，第1周冻结契约、第2周开始用固定响应联调。钱也算了：288乘30是8640，加服务器300、域名60，大约9000；年度维护5000只是后续参考。最后定下初稿时间，吴梓豪统稿，10月30日前交。",
]

doc = Document(str(SAMPLE))
body = doc.element.body

# Keep only the section properties; rebuild all visible content from the sample's paragraph templates.
sect_pr = body.find(qn("w:sectPr"))
for child in list(body):
    if child is not sect_pr:
        body.remove(child)

# Take paragraph templates from the original sample before rebuilding.
sample = Document(str(SAMPLE))
title_tpl = deepcopy(sample.paragraphs[0]._p)
body_tpl = deepcopy(sample.paragraphs[2]._p)
empty_tpl = deepcopy(sample.paragraphs[1]._p)

def set_single_run_text(p_el, text):
    runs = p_el.findall(qn("w:r"))
    if not runs:
        raise RuntimeError("template paragraph has no run")
    # Keep only the first run, then set its text.
    for extra in runs[1:]:
        p_el.remove(extra)
    run = runs[0]
    t = run.find(qn("w:t"))
    if t is None:
        t = run.makeelement(qn("w:t"), {})
        run.append(t)
    t.text = text
    t.set(qn("xml:space"), "preserve")

title_p = deepcopy(title_tpl)
set_single_run_text(title_p, TITLE)
title_para = Paragraph(title_p, doc._body)
title_para.paragraph_format.space_before = Pt(0)
title_para.paragraph_format.space_after = Pt(12)
sect_pr.addprevious(title_p)

for text in PARAGRAPHS:
    p = deepcopy(body_tpl)
    set_single_run_text(p, text)
    para = Paragraph(p, doc._body)
    para.paragraph_format.space_before = Pt(0)
    para.paragraph_format.space_after = Pt(8)
    para.paragraph_format.line_spacing = 1.0
    sect_pr.addprevious(p)

cp = doc.core_properties
cp.title = TITLE
cp.author = "第9组"
cp.subject = "第二次实验 TravelMind 项目开发计划"
cp.comments = "小组讨论记录"

OUT.parent.mkdir(parents=True, exist_ok=True)
doc.save(str(OUT))
print(OUT)
