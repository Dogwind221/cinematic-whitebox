# 白模镜头导演 · cinematic-whitebox

读取不同题材的剧本，以《繁花》的构图、人物光影与情绪节奏为默认方向，结合动作驱动运镜，指导 AI 在 Blender 中制作可编辑的白模剧情预演。

## 能做什么

- 通读剧本、拆分场景与叙事节拍，推导角色、场景和道具清单。
- 按剧情需要选用 15 位导演的代表镜头手法，说明适用条件、实现方式和失败条件；默认仍以《繁花》为主。
- 根据剧本语义选择风、重逢、告别、等待等意境手法，落实为角色、环境与相机的可播放变化；区分真实环境、比喻、否定和回忆。
- 设计景别、前景框景、留白、镜面、回头揭示、动作调度与剪辑切点。
- 把运镜写成显式字段（推进/拉远/横移/升降/环绕/变焦 + 缓动 + 取景跟踪），解算成相机路径并自检位移与放大倍率，避免运镜只停留在文字描述或坐标差暗示。
- 协调相机、焦点和动作，设计选择性的慢动作、抽帧与声音提示。
- 按关键帧、切点、动作连续性和剧情覆盖进行渲染检查。
- 制作任务交付 `.blend`、英雄机位图、白模预演视频及分镜和 QA 记录。

这是供 AI 编程代理读取的技能指令，不是 Blender 插件或独立的一键生成程序。实际制作需要可执行 Blender 操作的环境；可搭配 Blender MCP。不同剧本的完成度仍须通过实际渲染验证。

## 安装

把仓库克隆到个人技能目录，确保 `cinematic-whitebox/SKILL.md` 位于该目录下。已有同名目录时先备份或合并，不直接覆盖。

Windows PowerShell 示例：

```powershell
git clone https://github.com/Dogwind221/cinematic-whitebox.git "$env:USERPROFILE\.codex\skills\cinematic-whitebox"
```

## 使用

向支持此技能的代理提供剧本正文或可读取的文件，并输入：

> 使用 $cinematic-whitebox，完整读取这份剧本，以《繁花》摄影风格为主，自动拆场、推导资产和分镜，制作白模剧情预演并渲染验收。

也可以只要求分镜设计，或指定其他摄影风格。资产清单和参考视频为可选输入。建议提供画幅、目标片长和输出目录；未提供时技能会记录工作假设。

## 文件

- [SKILL.md](SKILL.md)：主要工作流程与验收要求。
- [意境到白模镜头](references/mood-routing.md)：剧情语义分支、风与重逢实现、分镜字段和路由自检。
- [情绪与美来源索引](references/mood-source-index.md)：124 条逐集抽帧研习记录，含时间码、观察、应用限制及重点连续时间补查。
- [电影美学合集应用](references/film-aesthetics-series.md)：14 集来源索引，补充转场、空镜、身体细节、光线维度、画幅与视点设计。
- [运镜选择与轨迹设计](references/camera-movement-design.md)：剧情触发、运动通道、起停、复合运镜与播放验收；含 `move` 显式字段规范与 `framing` 取景跟踪。
- [构图主次与空间层次](references/composition-hierarchy.md)：视觉平衡、框架、纵深、拉焦交接与灰阶分离。
- [摄影意图与验收](references/cinematography-intent.md)：机位、构图、运动的语境判断与替代方案比较。
- [导演手法选择](references/director-routing.md)：按叙事需要匹配导演手法，含相机、调度、剪辑与验收规则。
- [剧本到镜头](references/story-to-camera.md)：按叙事需要选择摄影方式。
- [《繁花》基础参考](references/fanhua-case.md)：构图、光影与参数使用边界。
- [《繁花》补充](references/fanhua-dongkente.md)：碎片切镜、回头、留白、镜面与音乐起落点。
- [动作驱动运镜](references/motivated-camera.md)：动作同步、焦点路径与切点衔接。
- [运镜解算器](agents/camera_motion.py)：把 `move` 声明（dolly/truck/pedestal/arc/zoom/static）解算成端点位移与焦距变化，并提供位移、放大倍率、构图漂移自检。可脱离 Blender 单独运行：`python agents/camera_motion.py`。

## 来源与验证范围

摄影风格来源：对《繁花》摄影艺术的研习，但独立实现。构图、光影与运镜方法由本项目自行归纳并重新实现，不复制该剧素材，与该剧制作方无关。

各参考文档标注视频链接、时间段以及观察与工程推导的区别。仓库不分发原视频、音频、字幕或抽帧，不代表原作者背书。

技能格式已校验；尚未对各种题材开展系统化端到端渲染测试。源自试作的经验不应当作对所有剧本的质量保证。
