# 记忆机制讲解

本 Agent 系统的重点是记忆机制，任务执行和记忆分离。系统分为 3 个角色：worker（干活）、summarizer（做摘要）、decider（判断是否要重置上下文）。

这么设计基于两个理由：
1. 拆分任务能减轻 AI 的注意力压力，从而达到更好的效果，这是 AI 工程的基本原则之一。
2. 人脑的记忆在很大程度上也是在后台自动完成摘要、重置的。

建议先阅读一下 `backend/src/core/init_prompts.py` 中的 `_build_codex_user_level_instruction`，以及 `backend/src/core/memory_manager.py` 中的 `build_summarizer_instruction` 和 `build_decider_instruction`，先留个大概的印象。

worker 的上下文每增长 3%，系统就自动从 worker 的上下文中 fork 一个 summarizer 和 decider 出来（利用缓存）。worker 不会暂停，而是会继续运行，就像人脑一样。这个设计会带来一些问题，后面会讲解决方法。

在 fork summarizer 出来**之后**，系统会在 worker 的上下文中留一个 `WAKE_SUMMARIZER_FLAG`。注意这里是**之后**，这个新加入的 flag 在当前刚 fork 出来的 summarizer 的上下文中是不存在的，这个 flag 是给下一次被唤醒的 summarizer 服务的，具体作用在 `build_summarizer_instruction` 里面有说明。
（其实系统并没有插入一个flag，系统是记录了一个隐性的flag，这里说有一个flag只是为了方便理解）

边界情况之一：上一个 summarizer 还没跑完，现在又到了一个触发 summarizer 的节点，这个时候就不要再新开一个 summarizer，而是等到下次触发再说。

系统检测到 decider 决定要重置上下文的信号后，就会暂停 worker，具体来说是在执行完 worker 的 tool call、系统 append 了 tool message 之后暂停运行。

![](docs/images/memory-explanation-zh-1.png)

![](docs/images/memory-explanation-zh-2.png)

红线划定的部分，是没有被摘要的，要把它放到新的上下文里面。原本的设计是打算再触发一次摘要。但是通常来说 decider 做决定不需要很长时间，这期间 worker 的上下文大概率不会增长很多，所以做摘要的话就有点浪费了，哪怕用了缓存也是这样。

如果 decider 发出了重置的信号，但是 summarizer 还没跑完，decider 就要等它跑完。

不能等到 decider 决定重置后再做摘要吗，这样更省 token？理论上可以。我之前在 Codex（`gpt5.2`）上也是等到我认为要重置了，才让它做摘要的，但是发现它会遗漏一些东西。

预计一年后，等大模型价格大幅下降了，可以调整成 worker 每工作五轮就唤起一次 summarizer 和 decider，甚至每工作一轮就唤起一次 summarizer，就像人脑那么频繁。

# 建议阅读顺序

1. `backend/src/core/init_prompts.py` 和 `backend/src/core/memory_manager.py`
2. `backend/src/core/agent.py`。Pycharm 里面点击 Structure，VS Code 里面点击 Outline 来查看 `Agent` 对外暴露了什么接口。核心是 `run()`。
3. `backend/src/core/agent_runner.py`：主要是为了照顾 steer conversation 功能，保证 agent 在有多条 steer message 进来的时候只运行一个 agent，防止重入。
4. `backend/src/web_app.py`
5. `backend/src/websocket_chat_session.py`

# 文档

- `AGENTS.md` 大致讲述项目的结构。
- `docs/feature-decisions.md`：产品功能决策
- `docs/draft-plans`：我自己写的初步计划
- `docs/plans`：AI 基于初步计划制定的计划

你可能需要把 `AGENTS.md` 中的 `# 用户开发环境` 一节给删掉。

# 启动

默认用 Codex 订阅，如果要用其他，需要先设置环境变量。

```bash
cd backend
cp .env.example .env
```

Linux/macOS:

```bash
chmod +x dev.sh
./dev.sh
```

用 Codex 可能需要设置环境变量来走代理，但 Pycharm 的 run configuration 不会展开环境变量里面的字面量，所以会导致代理设置失效。

可以直接在 run configuration 里面设置这个环境变量：
- key：`BIONIC_BOT_CODEX_HTTP_PROXY`
- value：`socks5h://172.17.16.1:7890`（如果你的 VPN 是 `7890` 端口）
