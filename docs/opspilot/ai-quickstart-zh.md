# 自然语言排程：快速上手

本项目有两部分：排程引擎负责计算，语言模型负责理解需求、整理输入和读取结果。
当前排程方法是 FCFS、EDD 和 CBC/MILP；强化学习、自动训练和网页麦克风尚未实现。

## 1. 启动与连接

先按 [README 的 Windows setup](../../README.md#windows-setup) 安装依赖、构建并启动。
打开 http://127.0.0.1:8000 。普通排程、比较、解释和导出不需要 AI。

使用自然语言入口前，需要选择并配置一个 AI 提供方：

- 本机订阅模式：安装官方 Codex CLI，登录自己的 ChatGPT 账户，确认 `codex login status`
  显示 ChatGPT 登录。在根目录 `.env` 中设置以下内容，再重启后端。
- Platform API 模式：设置 `AI_PROVIDER=openai_api`、自己的 `OPENAI_API_KEY` 和
  支持 low 推理设置的 `OPENAI_MODEL`。这是独立的 API 使用方式。

```dotenv
AI_ENABLED=true
AI_PROVIDER=codex_subscription
OPENAI_MODEL=gpt-6.1-sol
OPENAI_AGENTS_DISABLE_TRACING=true
```

CLI 不在 PATH 时，额外设置 `CODEX_PATH` 指向官方可执行文件。模型明确使用 low。
本机订阅模式只用于自己电脑上的 localhost 服务，受账户使用限制约束。
GitHub 的公开源码不包含登录凭据、本机 `.env`、数据库或虚拟环境。

## 2. 用口语描述订单

点击 **Describe workload**，例如输入：

> 我这边两台一样的机器。A 做四十分钟，九十分钟内必须完成；B 做二十分钟，
> 六十分钟内交。两个现在都能开工，时间都从现在算。

点击 **Interpret description**，检查订单、加工时间、可开工时间、交期和必须准时的标记。
没说清的关键内容会被追问；没指定开工时间和权重时，界面会列出默认值 0 和 1。
这些默认值需要你审核，不应当作原话中的事实。

可以直接改表格，之后点击 **Check edited draft**；也可以补充一句话后点击
**Add details and re-interpret**。勾选 **Approve workload draft**，填写名称，最后点击
**Confirm and create plan**。确认之前不会保存新订单或开始排程。

目前输入框接收文字。想直接说话，可以用系统语音听写将语音转成文字填入。

## 3. 看结果与比较方案

- FCFS、EDD 是基准方法；MILP 会在设置的时间预算内尝试优化。
- **Plan commitments / What-if** 可以要求选定订单按原交期完成，或增加一台相同机器。
  先预览，再确认生成新方案；原始订单和结果保留。
- **Scenarios** 查看保存的方案；**Explain** 查看实际指标变化及每个订单的贡献。
- **Copilot** 可以查询延期订单、机器利用率，或提出受支持的方案建议。
  提案需要确认；它尚不是能自由执行任何要求的决策助手。

“已找到可行方案”和“已证明最优”含义不同。超时未找到方案不等于已证明无解。
硬交期无解时不会显示虚构的指标。增加机器的比较反映排程效果，不计算购买回报。

## 范围与详细文档

输入支持 1–5 台相同机器、1–50 个单工序订单，时间为共同起点后的整数分钟，
权重为 1–10。增加机器的派生方案最多六台。不同机器能力、换线、班次、故障、
工序先后关系等尚未建模；不能直接把这些要求当成已支持的约束。

- [自然语言字段、接口和确认规则](natural-language-workloads.md)
- [硬交期、方案比较和解释](ai-planning.md)
- [Copilot 配置、工具与边界](copilot.md)
- [已执行的验证记录](natural-language-checks.json)
