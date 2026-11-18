# 免费离线词库复查 · 2026-10-20

## 结论

此次没有找到在“中文好理解、常见用法分清、免费完整离线”三项上，足以证明值得整体替换当前词库的来源。因此保留 Leaf 当前数据，没有修改程序、生词本或复习计划。这是本次检索和样例比较的结论，不代表对所有词典的质量排名。

## 当前实际安装的版本

本地 `data/learner.sqlite3` 的元数据为 **Leaf corrected learner data 1**，共 **84,236 个词条**。基于 Open Dictionary v2.0，并包含 Leaf 的缺词补充、义项修订和展示分组；ECDICT 只作补充。

本次直接核对上游 GitHub 发布接口：最新正式版仍为 **v2.0**，发布时间为 2026-08-05，尚无更新的发布包可升级。

- [上游正式发布](https://github.com/ahpxex/open-dictionary/releases/tag/v2.0)
- [最新发布元数据](https://api.github.com/repos/ahpxex/open-dictionary/releases/latest)
- [本地首轮审校记录](first-pass.md)

## 候选来源与取舍

| 来源 | 本次核实到的情况 | 决定 |
| --- | --- | --- |
| Open Dictionary | 当前已使用其最新正式版，并有本地修订 | 保留 |
| TICKurt English Dictionary Web | README 所指的 Open English Dictionary 会跳转到同一个 Open Dictionary 仓库 | 是使用同源数据的客户端，不能当成新词库升级 |
| IsDict | 混合 Wiktionary、ECDICT 等来源；抽查 demagogic、inform，仍有短中文译词配英文定义、旧义靠前的情况 | 不作为当前中文学习释义的替代 |
| Vocab Bloom Hub English 0.2.0 | 可下载开放数据，含中文概览；逐义中文和例句支持与现有库不同，样例没有显示整体优势 | 不整体替换，未导入 |
| Lexica | 自述合并 ECDICT、WordNet、Tatoeba、GCIDE 和中文维基百科；大量词条与词组增加覆盖 | 未发现新的成段中文学习释义来源，不因收词数量更大而替换 |
| Collins / 朗文 | 没找到符合免费完整离线接入条件的官方词库；Collins API 不允许用缓存代替查询，LDOCE5 Viewer X 要求用户提供已购 DVD 数据 | 未接入 |

来源：

- [TICKurt 项目与数据链接](https://github.com/TICKurt/english-dictionary-web)
- [IsDict 项目](https://github.com/simp-lee/isdict-api)
- [Vocab Bloom Hub 数据卡](https://huggingface.co/datasets/Fristail27/vocab-bloom-hub-en)
- [Vocab Bloom Hub 数据质量说明](https://github.com/Fristail27/vocab-bloom-hub/blob/main/docs/data.md)
- [Lexica 数据来源](https://github.com/liu-x27/lexica#the-dictionary)
- [Collins API 使用条款](https://blog.collinsdictionary.com/terms-conditions-collins-api/)
- [LDOCE5 Viewer X 数据要求](https://github.com/umlx5h/LDOCE5ViewerX)

## 实际样例比较

读取本地词库的实际显示结果，并与 Vocab Bloom Hub 的 demagogic、inform、field、credo、choppy、subtle 六个词条对照；另抽查 IsDict 的 demagogic、inform。没有以项目宣传的条目数量或测试数量代替内容检查。

| 词 | 观察结果 |
| --- | --- |
| demagogic | IsDict 的详细解释仍指向 demagogy / demagogue，中文只有短译。当前 Leaf 已解释这种言论怎样靠情绪争取支持。Vocab Bloom Hub 的概览也能讲清，但不足以证明有升级优势。 |
| inform | Vocab Bloom Hub 包含“塑造、影响”的英文义项，但中文概览只概括传递信息；这个义项的中文仍只有“影响”。当前 Leaf 的核心概览明确包含 be informed by，配有中文说明和双语例句。 |
| field | Vocab Bloom Hub 把接球与回答问题放在同一个具体义项中；当前 Leaf 分开解释。其名词概览可读，但动词概览主要讲接球，不能证明比当前概览更完整。 |
| credo | 两者中文概览都能表达指导行为的信念或原则；未发现足以支持替换的收益。 |
| choppy | Vocab Bloom Hub 的概览简洁，但水面义的中文短译为“波涛汹涌”；当前 Leaf 明确说明小而不规则的浪、不一定是巨浪，并给出中英对照例句。 |
| subtle | Vocab Bloom Hub 有中文概览，但第一个具体义项的中文仍为“微妙的”。当前 Leaf 在概览和具体义项中都解释“不容易察觉、表达含蓄”等含义。 |

以上是样例层面的编辑判断，不能外推为全库准确率。Vocab Bloom Hub 自己也注明内容由模型生成，尚无系统人工审定的子集；当前 Open Dictionary 同样不是全库逐条人工审定，因此不能把保留现有词库描述成“保证准确”。

样例页：

- [IsDict · demagogic](https://isdict.com/word/demagogic)、[inform](https://isdict.com/word/inform)
- [Vocab Bloom Hub · demagogic](https://vocab-bloom-hub.com/zh/word/demagogic)、[inform](https://vocab-bloom-hub.com/zh/word/inform)、[field](https://vocab-bloom-hub.com/zh/word/field)、[credo](https://vocab-bloom-hub.com/zh/word/credo)、[choppy](https://vocab-bloom-hub.com/zh/word/choppy)、[subtle](https://vocab-bloom-hub.com/zh/word/subtle)

## 执行范围

只读取当前词库、公开项目说明及公开样例，并新增这份比较记录、更新选型文档的状态说明。未下载新整库，未覆盖当前释义，未修改用户数据。没有程序变更，因此未重新打包或重复执行程序测试。
