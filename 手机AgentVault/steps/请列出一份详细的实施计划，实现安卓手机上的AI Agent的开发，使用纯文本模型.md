这份实施计划将指导你从零开发一个**基于纯文本模型（不依赖视觉/截图）**的 Android AI Agent。 
**核心优势**：
* **成本极低**：使用 DeepSeek-V3、GPT-4o-mini 或本地 Llama-3，单次操作成本仅为视觉方案的 1/100。 
* **响应极快**：传输文本数据（KB级）远快于图片上传（MB级）。 
我们将开发过程分为三个阶段：**Python原型验证 (MVP)** -> **算法优化** -> **端侧移植 (Android App)**。 --- 
### 阶段一：Python + ADB 原型验证 (MVP) 
**目标**：在 PC 上运行 Python 脚本，控制连接的 Android 手机，验证“获取XML -> 决策 -> 执行”的闭环。 
#### 1. 环境准备 
* **硬件**：PC (Windows/Mac/Linux)、Android 手机（开启开发者模式 -> USB 调试）。 
* **软件**：Python 3.10+、Android SDK Platform-Tools (ADB)。 
* **依赖库**： ```bash pip install openai lxml pure-python-adb ``` 
#### 2. 核心模块开发 你需要编写三个 Python 文件： 
* **`perceptor.py` (感知层)** * **功能**：调用 ADB 获取 XML，清洗数据。 
	* **关键逻辑**： 
	1. 执行 `adb shell uiautomator dump` 获取布局。 
	2. 使用 `lxml` 解析 XML。 
	3. **数据清洗（关键步骤）**： 
		* 遍历所有节点。 
		* **过滤**：只保留 `clickable="true"` 或 `checkcable="true"` 或 `text` 不为空的节点。 
		* **提取特征**：提取 `resource-id` (控件ID), `content-desc` (无障碍描述), `text` (显示文本), `bounds` (坐标范围)。 
		* **坐标计算**：将 `bounds="[x1,y1][x2,y2]"` 转换为中心点 `(center_x, center_y)`。 
		* **生成 ID**：给每个有效节点分配一个简短的数字 ID（如 1, 2, 3...），方便 LLM 引用。 
* **`brain.py` (决策层)** 
	* **功能**：构建 Prompt，调用 LLM API。 
	* **Prompt 设计策略**： 
		* ```text 系统提示：你是一个 Android 自动化助手。你无法看到屏幕，只能阅读 UI 布局数据。 输入数据格式： [ID] <类型> "文本内容" (ID名: resource_id) 示例： [1] <Button> "确认" (ID: com.app:id/confirm_btn) [2] <ImageView> "" (ID: com.app:id/back_icon, Desc: 返回) 当前任务：{用户指令} 要求： 1. 分析 resource-id 和 content-desc 来推测没有文本的图标含义。 2. 返回 JSON 格式：{"action": "click", "element_id": 1, "reason": "点击确认按钮"} 3. 如果需要输入文本，返回：{"action": "input", "element_id": 5, "text": "你好"} ``` 
* **`executor.py` (执行层)** 
	* **功能**：接收指令并执行。 
	* **实现**： * 点击：`adb shell input tap <x> <y>` * 输入：`adb shell input text <string>` (注意处理空格和特殊字符) * 滑动：`adb shell input swipe <x1> <y1> <x2> <y2>` 
#### 3. 运行流程 
编写 `main.py` 将上述串联：
> `Loop`: 获取 XML -> 清洗为 List -> 发送给 LLM -> 解析 JSON -> 执行 ADB 命令 -> `Sleep(2s)` -> 下一轮。 --- 
> 
### 阶段二：算法与稳定性优化 (数据工程) 
纯文本方案最大的痛点是**信息丢失**（比如一个按钮只有图标，没有 `text` 也没有 `content-desc`）。此阶段重点解决这个问题。 
#### 1. 增强型数据清洗 (Heuristics) 
LLM 看不到图标，但我们可以帮它“猜”。 
* **Resource ID 语义映射**： 
	* 如果 `resource-id` 包含 `search`, `magnifier` -> 标注为 [可能代表搜索]。 
	* 如果 `resource-id` 包含 `hamburger`, `menu`, `drawer` -> 标注为 [菜单]。 
	* 如果 `resource-id` 包含 `back`, `return` -> 标注为 [返回]。 
* **结构推断**： 
	* 如果一个 `ImageView` (无文字) 旁边紧挨着一个 `TextView` (有文字)，且它们父节点相同，可以将它们视为一个整体组合，把文字赋给那个图片。 
#### 2. 引入“记忆” (Context) 
* **短期记忆**：将最近 3 步的操作历史放入 Prompt。 
	* *作用*：防止死循环。如果 AI 连续 3 次点击同一个无效按钮，它可以通过历史记录发现并尝试其他路径。 
* **错误修正**： 
	* 如果 LLM 返回的 `element_id` 不存在，程序捕获错误，自动将错误信息反馈给 LLM 让其重试，而不是崩溃。 --- 
	* 
### 阶段三：端侧移植 (Android App - 最终形态) 
摆脱电脑，做成一个安装在手机上的 App。 
#### 1. 技术栈变更 
* **语言**：从 Python 切换到 **Kotlin/Java**。 
* **核心服务**：**AccessibilityService (无障碍服务)**。 
	* *优势*：相比 ADB，无障碍服务获取界面节点是毫秒级的，且不需要 Root 权限，不需要连接电脑。 
#### 2. 开发步骤 
1. **创建 Android 项目**：配置 `AndroidManifest.xml` 声明 `BIND_ACCESSIBILITY_SERVICE`。 
2. **实现 AccessibilityService 类**： * 重写 `onAccessibilityEvent()`：监听屏幕变化。 * 使用 `getRootInActiveWindow()`：这直接返回当前的节点树（等同于之前的 XML）。 
3. **节点转文本 (Kotlin实现)**： * 编写递归函数遍历 `AccessibilityNodeInfo` 树。 * 提取 `text`, `contentDescription`, `viewIdResourceName`。 * 构建简化版的 JSON 字符串。 
4. **网络请求**： * 在 Android 中使用 OkHttp/Retrofit 调用大模型 API (DeepSeek/OpenAI)。 * *注意*：API Key 不要硬编码，建议让用户在设置页填入。 
5. **执行操作**： * 不再需要 ADB。直接调用 `node.performAction(AccessibilityNodeInfo.ACTION_CLICK)`。 * 对于输入文字：`node.performAction(ACTION_SET_TEXT, bundle)`。 
#### 3. 悬浮窗交互 (UI) 
* 开发一个悬浮球（Floating Window）。 
* 用户点击悬浮球 -> 弹出语音/文字输入框 -> 触发 Agent 流程。 --- 
* 
### 实施时间表参考 (2周 Sprint) 
| 时间          | 任务                           | 产出              |     |             |                             |                 |     |             |                            |                 |     |              |                              |             |     |               |                          |        |                                                                                                                                                                                                                                                                                                                                                                                                |
| :---------- | :--------------------------- | :-------------- | --- | ----------- | --------------------------- | --------------- | --- | ----------- | -------------------------- | --------------- | --- | ------------ | ---------------------------- | ----------- | --- | ------------- | ------------------------ | ------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Day 1-2** | 环境搭建，调试 `adb dump`，解析 XML 结构 | 能够打印出清洗后的 UI 列表 |     | **Day 3-4** | 对接 LLM API，编写 Prompt，调试点击坐标 | 能够完成简单的“打开设置”任务 |     | **Day 5-6** | **难点攻关**：优化无文字图标的识别逻辑，处理弹窗 | 成功率提升，能处理复杂 App |     | **Day 7-10** | (可选) 移植到 Android App，实现无障碍服务 | 独立的 APK 安装包 |     | **Day 11-14** | 增加多轮对话支持，测试微信/支付宝等常用 App | 最终交付版本 | ### 成本与风险提示 1. **API 成本**： * 使用 GPT-4o-mini 或 DeepSeek-V3，每一步操作成本极低（约 0.001元人民币）。 2. **最大的坑：WebView 与 游戏**： * **风险**：Flutter、React Native 应用、Unity 游戏以及部分银行 App 的 WebView 可能不暴露无障碍节点信息（即 XML 是空的或只有一大块 View）。 * **应对**：这是纯文本方案的硬伤。如果遇到这种情况，必须抛出异常提示用户“无法识别当前界面”，或者（如果预算允许）在此时临时回退到截图方案。 3. **隐私**： * 上传 UI 布局数据到云端 LLM 涉及隐私。如果是做商用产品，必须在隐私协议中声明，或者考虑使用端侧小模型（如 Google Gemini Nano 或 MobileLLM）。 |


**最大的坑：WebView 与 游戏**： * **风险**：Flutter、React Native 应用、Unity 游戏以及部分银行 App 的 WebView 可能不暴露无障碍节点信息（即 XML 是空的或只有一大块 View）。