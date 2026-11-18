# 旧生词导入与核心释义重写 · 2026-11-02

来源是桌面的 `words.md`。原文件保留不动，文件内容仅作为待整理数据，不作为操作指令。

## 核对方法

先以完整词条模式解析，再独立按每个 `•` 标记切分重查，包括 Part 63 同一行的三个词。两种提取方法都读到 **865 条记录**，共 **841 个不同的原始词头**。重复记录合并；`Sciatic/Sciatica` 分为形容词 `sciatic` 和疾病名词 `sciatica`，得到 **842 个不同的词和短语**。

保留词形与短语的区别：例如 `cede` 与 `ceded`、`guerrilla` 与 `guerrillas` 分别保留；同一拼写不分大小写只留一个生词。没有为了减少数量，把名词复数、动词或含义不同的派生词强行归并。

整理前生词本有 **137 条**，其中 68 条与旧文件重合，另有 69 条只在生词本中。因此新增 **774 条**，合并后共 **911 条**。现有卡片的原句、来源、创建日期、暂停状态、FSRS 计划以及 **49 条复习记录**均原样保留。新增词按原有机制创建为未复习卡片，没有伪造任何练习历史。

## 释义编写与复查

全部 **911 条核心释义**均重新编写，写成简洁的自然中文，存入“我的释义”，供查词、生词本、复习统一显示。不是直接把原笔记的情绪联想整段搬入，也不把缺乏依据的历史情景当成单词自带的含义。

完成后重新核对了多义词、词形、语体和容易混淆的专业词。重点修正包括：

- `omniscient` 是“全知”，不包含“全能”；`fasces` 是束棒，不是“法西斯主义”的同义词。
- `regime` 不必是独裁政权，`coalition` 不自动表示脆弱；`anarchism` 也不能直接等同于无法无天。
- `patrons`、`barges` 补清名词复数含义，避免只显示动词的词形说明。
- `tuberculosis` 是结核病，不只指肺部；`ulcer` 不是肿瘤；`sciatic` 与 `sciatica` 分开解释。
- `cash in` 区分兑现与 `cash in on` 的利用获利；死亡委婉语通常是完整的 `cash in one's chips`。
- `for if` 解释为相邻的两个连词；`with bearing of` 提醒结合完整表达 `with the bearing of…` 阅读。
- `interment` 与 `internment`、`loath` 与 `loathe`、`wary` 与 `weary` 等区别加以说明。

每条释义 25–68 个字符左右，优先常用义；这是供个人阅读学习使用的整理，不是整套商业词典的替换。

较少见、专业或易混淆条目的核对参考包括 [Collins · boulevardier](https://www.collinsdictionary.com/dictionary/english/boulevardier)、[pictorialist](https://www.collinsdictionary.com/us/dictionary/english/pictorialist)、[impeachable](https://www.collinsdictionary.com/dictionary/english/impeachable)、[Cambridge · easement](https://dictionary.cambridge.org/us/dictionary/english/easement)、[CDC · blackwater fever](https://wwwnc.cdc.gov/eid/article/29/4/22-1267_article/)、[NHS · tuberculosis](https://www.nhs.uk/conditions/tuberculosis-tb/)、[sciatica](https://www.nhs.uk/conditions/sciatica/)、[codeine](https://www.nhs.uk/medicines/codeine/)。中文为重新组织的解释，不是商业词典整条复制，也不提供诊疗或法律操作建议。

## 数据与检查文件

- `manifest.json`：完整原始记录、行号、重复项映射、原生词本快照与原文件校验值。
- `definitions-01.psv` 至 `definitions-10.psv`：逐词编写的 911 条核心释义。
- `definitions.json` / `全部核心释义.md`：合并后的释义清单。
- `rehearsal-verification.json`：在独立数据库副本上演练后的逐词检查。
- `final-verification.json`：写入正式生词本之后的逐词核对。
- `after-import-backup.json`：整理后的完整学习数据备份。

检查同时覆盖：原文件每条记录均有对应词、没有重复卡片、没有空白释义、911 次查词与 911 次复习释义处理结果和预期文字逐字一致、原有进度和复习日志保持不变、数据库完整性与外键检查通过。自动检查判断覆盖和保存是否正确，不等于证明每一个词义绝无错误。

升级及导入前的完整数据库备份保存在 `user_data/backups/`，包括 `before-words-import-*` 与 `before-reviewed-words-import-*`。原先手动写过的释义也在这些备份内。
