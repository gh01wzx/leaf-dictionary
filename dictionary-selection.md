# 词典选型结论

> **当前状态（2026-10-20）**：Leaf 已接入 Open Dictionary v2.0 的本地修订版，共 84,236 个词条。下文记录的是早期选型过程，其中“尚未接入”“尚待回复”描述的是当时状态。最新一轮比较没有发现值得整体替换的免费离线来源，详见 [2026-10-20 比较记录](reviews/dictionary-comparison-2026-10-20.md)。

按“常用意思讲清楚、使用自然句子解释、避免生僻义堆积”选择，首选 **Collins COBUILD 学习词典**，补充选择 **Longman Dictionary of Contemporary English / 朗文当代高级双解**。

注意：COBUILD 学习词典不等于 Collins English Dictionary 综合词典；同一个网页可能连续列出它们及其他词典的不同版本。不能不分来源全部导入。

## 已核对的依据

- Collins 官方介绍：COBUILD 使用完整句子的释义方式，利用语料中的频率、意义和搭配信息安排词义的重要性和对学习者的实用性。
  https://blog.collinsdictionary.com/the-history-of-cobuild/
- Collins 官方产品介绍：Learner's Dictionary 以简单、自然的英文完整句子解释。
  https://collins.co.uk/products/9780008607760
- Pearson 官方产品说明：朗文当代第六版以约 2,000 个常见词编写定义。
  https://www.pearsonelt.es/content/professional/english/pearsonelt-es/en/catalogue/Dictionaries/Longman-Dictionary-of-Contemporary-English-6th-edition.html
- 牛津学习词典用 Oxford 3000 编写释义，也是优秀候选；但“最多词条”或历史性大词典不是本需求的优先标准。
  https://www.oxfordlearnersdictionaries.com/about/oxford3000

## 实际条目检查

核对了 Collins 和 Cambridge 的 field 条目：土地、体育场地、研究或工作领域应分清；field questions 是动词搭配；电场、数据库字段等有领域标签。field 作定语的词性标注会因词典分析而不同：COBUILD 确实列出 adjective 用法，不能简单判定截图词性错误。

https://www.collinsdictionary.com/dictionary/english/field
https://dictionary.cambridge.org/dictionary/english/field

## 完整离线数据：尚未取得

- Collins 的官方 API 不是可离线缓存的完整下载渠道；其 API 条款明确不允许以离线储存替代 API 请求。
  https://blog.collinsdictionary.com/terms-conditions-collins-api/
- Oxford 官方 FAQ：离线存储需要另行的数据许可。此产品也不必然等于 OALD 学习词典。
  https://developer.oxforddictionaries.com/faq
- Cambridge 官方 API FAQ：离线存储需另行协商许可。
  https://dictionary-api.cambridge.org/api/faq
- LDOCE5 Viewer X 是离线阅读器，不自带朗文词库；它要求使用者提供购买的 DVD 中的 ldoce5.data。
  https://github.com/umlx5h/LDOCE5ViewerX
- Pearson 香港数字资源页存在第五版离线程序，但列出的依赖包含旧 Flash；未验证可用于本应用的可读词库，也未把它当作已经接入的解决方案。
  https://digital-resource.upephk.com/?p=123090

本次还检索到第三方上传的 MDX、PDF 和阅读器仓库。它们的出版社版本、数据来源和整库使用条件无法据此确认，因此不能宣称已取得正版、完整、可接入的学习词典。

## 原型的真实状态

0.3 已停止初始化大模型。当前内容仍是原有 ECDICT 加本地整理条目，不是 COBUILD 或朗文。field 提供一个参考权威词典整理的中文呈现示例，明确标明来源与范围；它不代表完整词库已经替换。

已有生词、原句、备份及学习记录保留。旧模型内容作为历史记录保留，不再用于新查询。完整高质量学习词库的取得和接入仍未完成。
# 补充：免费离线的另一种数据来源（尚未接入）

2026-10-15 发现 [Open Dictionary v2.0](https://github.com/ahpxex/open-dictionary/releases/tag/v2.0)：发布说明标注 84,212 个词条，提供 JSONL 和 SQLite 完整下载，数据以 CC BY-SA 4.0 发布。它由 Wiktionary / Wiktextract 数据经模型预先扩写为固定的简体中文学习释义，包含 core/common/rare 分级、中文说明和双语例句。使用成品数据可以完全离线，不需要在用户电脑运行模型，也不需要付费 API。

这与人工编纂的商业学习词典不同，不能标成 COBUILD、朗文，也不能把项目自称的校验当成逐条人工审定。已读取发布元数据和三条实际释义，未下载完整词库、未接入本应用。由于用户此前明确要求从大模型换回词典，已询问是否接受这种预先整理的数据来源，尚待回复。

