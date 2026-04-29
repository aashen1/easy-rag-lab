QUESTION_TYPES = {
    "single_fact": "单知识点查询",
    "multi_fact": "多知识点综合",
    "reasoning": "推理型问题",
    "comparative": "对比分析",
    "missing": "缺失知识点",
    "irrelevant": "无关问题",
    "adversarial": "对抗性问题",
}

TYPE_DISTRIBUTION = {
    "single_fact": 0.25,
    "multi_fact": 0.20,
    "reasoning": 0.15,
    "comparative": 0.15,
    "missing": 0.10,
    "irrelevant": 0.05,
    "adversarial": 0.10,
}

DOCUMENT_TRUNCATE_MAX = 8000

GOLDEN_TYPE_DISTRIBUTION = {
    "single_fact": 0.15,
    "multi_fact": 0.18,
    "reasoning": 0.15,
    "comparative": 0.15,
    "missing": 0.12,
    "irrelevant": 0.05,
    "adversarial": 0.20,
}

FAILURE_MODES = {
    "single_fact": "基础检索失败：精确数据/事实无法被检索到",
    "multi_fact": "多跳检索失败：需要整合多个信息点但系统只返回部分",
    "reasoning": "推理能力不足：无法基于检索到的信息进行逻辑推断",
    "comparative": "对比分析失败：无法跨段落/跨文档对比信息",
    "missing": "拒答能力不足：文档中没有的信息未能正确识别，产生幻觉",
    "irrelevant": "幻觉控制失败：无关问题产生了看似相关的编造内容",
    "adversarial": "边界场景翻车：数字近似/跨文档混淆/时序陷阱等",
}

MIN_QUOTE_LENGTH = 30

MIN_QUOTE_LENGTH_DEFAULT = 30

MIN_QUOTE_LENGTH_CJK = 15

EVIDENCE_MAX_TOKENS = {
    "comparative": 2048,
    "reasoning": 2048,
    "multi_fact": 2048,
}

ANSWER_LENGTH_LIMITS = {
    "single_fact": 200,
    "missing": 200,
    "irrelevant": 200,
    "adversarial": 200,
    "multi_fact": 300,
    "comparative": 300,
    "reasoning": 350,
}

DOMAIN_KEYWORDS = [
    "增长",
    "下降",
    "上升",
    "减少",
    "增加",
    "收入",
    "利润",
    "营收",
    "市值",
    "占比",
    "规模",
    "产量",
    "销量",
    "价格",
    "成本",
    "投资",
    "融资",
    "估值",
    "盈利",
    "亏损",
    "负债",
    "资产",
    "现金流",
    "毛利率",
    "净利率",
    "ROE",
    "ROA",
]

PROPER_NOUN_SUFFIXES = [
    "股份",
    "集团",
    "公司",
    "行业",
    "市场",
    "技术",
    "产品",
    "业务",
    "报告",
    "年度",
]

PROPER_NOUN_PATTERN = r"[\u4e00-\u9fff]{2,8}(?:" + "|".join(PROPER_NOUN_SUFFIXES) + ")"

VALIDATION_STRICTNESS = {
    "single_fact": "strict",
    "adversarial": "strict",
    "multi_fact": "moderate",
    "comparative": "moderate",
    "reasoning": "lenient",
    "missing": "none",
    "irrelevant": "none",
}
