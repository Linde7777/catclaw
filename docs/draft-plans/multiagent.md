背景是这样的，我这个 agent 系统不是会自动 fork agent出来吗，就是 fork summarizer和decider出来，我这个系统将来也是要做 Multi Agent 支持的，然后呢，我现在 summarizer 和 decoder 的它的工作过程都是通过日志来显示的，就是不太方便嘛，就是所以说因为我将来也要做 multi agent，那么所以我也要专门做个 UI 出来。那么我就希望现在这个 summarizer 和 decoder 也能复用这个multiagent的相关的前端和（或者）后端代码。

summarizer/decider 不会有暂停、steer conversation 这种功能。

ui方面，是要弄一个类似side panel的效果，在右边侧边栏里面弄，你可以查看每个 subagent 的 完整工作过程，是你看它的过程就是和我们看主agent的工作过程是一样的。

agent可以创建subagent，subagent没有任何记忆机制，它们是临时创建的，用来给agent减轻上下文压力。Subagent 的聊天过程还是要持久化到文件里面的，用于审查。

要有一个工具叫做Create subagent，参数是subagent的名字（要是唯一的）。还有一个first msg参数，就是就是给这个subagent的第一句话，就是说交给他的任务吧。

我要做基于Steer conversation做一个multiagent沟通机制。

要有一个工具叫做send_msg_to_agent，参数agent_name和msg，底层就是通过submit user message

agent A调用这个工具给agent B发送消息时，agent B会收到：
```
<msg from="A">some content</msg>
```
这个xml是系统自动加上的

我感觉应该要在 WebSocket chat session 和 Agent Runner 之间，应该是要在加一个抽象，这个抽象会包住 Agent Runner， 就是说这抽象是专门用来处理多 Agent 的。

subagent, decider, summarizer 的聊天记录都要持久化到文件里面

Subagent可以再创建subagent（这个是可以配置的。如果把这个配置关了，那么 subagent 就不能再创建 subagent，默认关闭。）
