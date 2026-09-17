# ASS 双语字幕英文标点空格修复工具

一个专门处理 **中英双语 `.ass` 字幕**里英文行标点空格问题的命令行小工具：标点前多了空格、标点后少了空格、缩写被拆散、说话人横线间距不对……这些字幕组人工排版或格式转换时很容易引入的小毛病，用它可以批量检查、安全修复，拿不准的地方绝不瞎猜，而是列进人工复核清单。

纯 Python 标准库实现，**无第三方依赖**，需要 Python 3.10+。

## 这是做什么的

双语字幕的英文行经常出现这类问题（左边是原文，右边是修复后）：

```text
What are you doing ?          ->  What are you doing?
Wait...I don't know.          ->  Wait... I don't know.
We 're leaving now.           ->  We're leaving now.
- Hi. - Hello.                ->  - Hi.  - Hello.
Stop!.                        ->  Stop!
gold-plated,.50 caliber       ->  gold-plated, .50 caliber
```

本工具会扫描 `.ass` 文件里 `Dialogue` 事件中**含拉丁字母且不含中日韩文字**的可见分行（也就是英文行，包括常见的 `中文\N{\r样式}English` 双语结构），只调整这部分文本的标点和空格，不做任何翻译或拼写修正，也不会触碰中文行。

## 核心特性

- **原字幕永不覆盖**：只在单独的输出目录里生成修复后的副本，出问题随时可以丢弃重来。
- **拿不准就不改**：所有规则都刻意保守，遇到无法确定原意的结构（例如引号跨字幕、`1No` 疑似把横线打成数字、可疑的倒装标点等），保留原文并自动列入人工复核清单，而不是猜一个答案。
- **大量真实场景保护规则**，包括但不限于：
  - 常见缩写与首字母缩略词：`Ph.D.`、`A.M.`、`S.H.I.E.L.D.`、`Jr.`、`I.D.'d` 等,不会被句号拆散；
  - URL、邮箱、域名、数字（含千分位、小数、`.50` 这类省略整数部分的小数）；
  - 说话人横线间距（后一说话人前两格、说话人后一格）与承接省略号（`- ...hello`）；
  - 歌词符号 `*`、`♪`、`♫` 包裹的边界间距；
  - 跨字幕事件的引号闭合关系（引用可能横跨多条字幕）；
  - 西班牙语倒装标点 `¿`、`¡`；
  - 高置信度的缩写自动合并（`we 're` → `we're`、`do n't` → `don't`）与冗余标点清理（`What.?` → `What?`）。
  - 支持通过 `--protect` 追加自定义专名/缩写，无需改代码。
- **二次运行结果稳定（幂等）**：修复后的文本不会在下次运行时又被改一遍；如果发现会变化，会拦截并转入人工复核（`NOT_IDEMPOTENT`）。
- **编码兼容**：自动识别 UTF-8 (含 BOM)、UTF-16、GB18030 等常见字幕编码，原样写回；报告文件始终使用 UTF-8。

## 快速开始

### 批量生成修复副本

```powershell
python fix_english_punctuation_spacing.py "D:\Movies" --recursive
```

- 只有**本次确实发生自动修改**的 `.ass` 才会输出，并保留原有子目录结构；完全未修改或仅命中人工复核的文件不会被复制。
- 修复副本默认写入 `D:\Movies\punctuation_fixed`（可用 `--out-dir` 自定义）。再次扫描同一源文件时，如果它已经不需要修改，脚本会自动删除上次遗留的对应副本，避免旧文件被误认成本次结果。
- 完整报告：`punctuation_fixed\punctuation_fix_report.txt`（每个问题的原文件行号、完整 BEFORE/AFTER，无条数上限）。
- 人工复核清单：`punctuation_fixed\punctuation_manual_review.txt`，列出可能需要人工介入的文件路径、原文件行号、原因说明和原文/建议结果，包括未修改但可疑的行。
- 单文件、或目录下只有一个 `.ass` 时，终端自动显示明细；多文件默认只显示汇总，加 `--details` 展开。

### 只检查，不生成任何文件

```powershell
python fix_english_punctuation_spacing.py "D:\Movies" --recursive --check
```

`--check` 会同时检查空格问题和人工复核疑点并打印报告，但不创建或更新任何字幕、目录或报告文件。终端放不下时可以自行重定向：

```powershell
python fix_english_punctuation_spacing.py "D:\Movies" --recursive --check --details | Out-File -LiteralPath "D:\Movies\spacing_check_report.txt" -Encoding utf8
```

### 自定义专名保护

遇到脚本不认识、又不希望被处理的特殊词（人名、机构名、专有缩写等），用 `--protect` 追加即可，不需要改代码：

```powershell
python fix_english_punctuation_spacing.py "D:\Movies" --recursive --check --protect "ACME.XYZ" --protect "Hooli.Chat"
```

`--protect` 的参数是字面文本而非正则，匹配不区分大小写但保留原文大小写；不接受空参数、空白或 ASS 标签/换行；只对本次运行生效，下次仍需重新传入。建议名称参数不带句末标点，这样句末空格仍能正常整理。

## 命令行参数

| 参数 | 说明 |
| --- | --- |
| `input`（位置参数） | 一个 `.ass` 文件，或包含 `.ass` 文件的文件夹 |
| `--recursive` | 递归扫描子文件夹（会自动排除本次输出目录） |
| `--check` | 仅检查并打印报告，不写入或修改任何文件 |
| `--out-dir DIR` | 输出目录，默认 `punctuation_fixed`；相对路径以输入目录为基准 |
| `--details` | 终端展开完整明细（磁盘报告始终包含全部细节，不受此参数影响） |
| `--protect TOKEN` | 保护一个自定义专名/缩写，可重复传入多个 |

## 人工复核说明

人工复核是**启发式筛选**，不是完整的语言校对。常见候选类型包括：疑似倒装标点错误、疑似把说话人横线打成数字 `1`、疑似单词粘连、结构可疑的引号、含义不明确的 `,.`、被意外拆开的数字或撇号，以及二次处理仍会变化的行等。**名单为空不代表字幕绝对正确**，专名或正常引用也可能被误报，需要人工确认。

## 测试

在脚本所在目录运行：

```bash
python -B -m unittest discover -v
```

仓库包含三个测试文件：

- `test_punctuation_spacing.py` —— 基础空格、说话人横线、缩写、倒装标点、引号与省略号等规则的常规测试；
- `test_spacing_round3.py` —— 针对历史误改案例（如 `Ph.D.`、`Wall.e`、跨字幕引号等）的回归测试；
- `test_spacing_tv.py` —— 剧集（TV）场景下的批量处理回归测试。

## 项目结构

```text
project_subtitle-comma/
├── fix_english_punctuation_spacing.py   # 主脚本：检查 / 修复 / 报告
├── test_punctuation_spacing.py          # 基础规则测试
├── test_spacing_round3.py               # 历史误改案例回归测试
├── test_spacing_tv.py                   # 剧集批量场景回归测试
└── Inception.2010...REMUX-FraMeSToR.ass # 示例/测试用双语字幕文件
```

## 已知限制

- 只处理 `Dialogue` 事件中含拉丁字母且不含中日韩文字的分行，不涉及翻译、措辞或拼写修正。
- 规则针对英文标点习惯设计，其他拉丁语系语言的标点习惯可能不完全适用。
- 旧版本脚本误改过的副本不保证能自动复原；更新脚本后建议直接从原始字幕重新生成副本，不要把旧的 `punctuation_fixed` 目录当作输入源。

## 许可证

仓库目前未包含 LICENSE 文件，发布到 GitHub 前请根据需要自行选择并添加合适的开源协议（如 MIT、Apache-2.0）。
