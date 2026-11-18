# Open Dictionary v2.0 实际释义抽查

本次仅供看质量，**没有替换 Leaf 的词库或修改生词本**。

下载来源：[Open Dictionary v2.0](https://github.com/ahpxex/open-dictionary/releases/tag/v2.0)。完整 JSONL 包含 84,212 个词条；压缩包与解压内容均通过发布方 SHA256 校验。选取 16 个与阅读场景相关的词进行检查，13 个命中，3 个未收录。这是有目的的选样，不代表全库覆盖率或准确率。

以下 `samples.md` 中的引文是数据包原文，没有为了展示效果改写。保留词库的 core/common/rare 标签，方便看出它实际如何划分常用程度。

## 抽查结论

- **credo、informed 的核心中文说明较清楚。** credo 不只是“信条”两个字；informed 能区分人掌握信息与决定基于充分信息，并提醒有根据不等于一定正确。
- **inform 包含原阅读句需要的“塑造、深刻影响”。** 但 informed 条目本身只说明形容词义，阅读中的被动动词结构仍要正确关联回 inform，不能直接套形容词解释。
- **demagogic、demagogical、demagogue 均未命中。** 已扫描整个文件，不能让这套词库单独承担兜底查询。
- **field 的概览说有“专业领域”义，详细义项却没有单独解释它。** 详细列表有田野、农田、运动场、物理场、字段等。物理场的用法说明又把“场”和“领域”混在一起，不能代替 a field of research 的学习释义。参见 [Collins field 第 5 义](https://www.collinsdictionary.com/dictionary/english/field)。
- **run 的用法说明自相矛盾。** 同一段先说“不能在这个意义下直接接表示路程的名词”，紧接着又给出 run a mile。这种限定会误导学习者；[Oxford mile 条目](https://www.oxfordlearnersdictionaries.com/us/definition/english/mile)也列有直接接距离的例句。
- **部分概览仍夹杂罕见义。** 例如 informed 的概览带入已废弃义，subtle 的概览提动词用法。bank 的记忆线索把不同词源强行串成“隆起”的单一形象，不适合当作可靠词源解释。

判断：中文可读性比现有基础简释更接近目标，但不能直接视为成熟、逐条人工审定的学习词典。值得继续试用有明确来源的词条，接入时需处理缺词回退、常用义缺失、形容词与动词形式的关联，以及原数据错误。

## 原始数据与署名

数据由 Open Dictionary 项目基于 English Wiktionary / Wiktextract 生成并发布。释义和例句含预先生成的内容，**不是我在抽查时新生成的解释**。它们按 [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) 许可提供；本次选摘保留该许可与对 Wiktionary 贡献者、Wiktextract 和 Open Dictionary 项目的署名。

- [逐词原文摘录](samples.md)
- [13 个完整原始词条](../downloads/open-dictionary-v2/review-samples.json)
- [发布方数据许可](https://github.com/ahpxex/open-dictionary/blob/main/LICENSE-DATA.md)
