import subprocess
import os
import re
from lxml import etree

class Perceptor:
    def __init__(self, adb_path="adb"):
        self.adb_path = adb_path
        self.temp_xml_path = "window_dump.xml"
        self.device_xml_path = "/sdcard/window_dump.xml"

    def _run_adb(self, command):
        """执行 ADB 命令的辅助函数"""
        full_cmd = f"{self.adb_path} {command}"
        try:
            result = subprocess.run(
                full_cmd, 
                shell=True, 
                check=True, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE
            )
            return result.stdout.decode('utf-8')
        except subprocess.CalledProcessError as e:
            print(f"ADB Error: {e.stderr.decode('utf-8')}")
            return None

    def capture_layout(self):
        """
        核心步骤1: 获取屏幕布局 XML
        """
        # 1. 在手机上生成 dump 文件
        # 注意：有些手机可能需要加 --compressed 参数，或者使用 uiautomator v2
        print("正在获取屏幕布局...")
        self._run_adb(f"shell uiautomator dump {self.device_xml_path}")
        
        # 2. 拉取到本地
        self._run_adb(f"pull {self.device_xml_path} {self.temp_xml_path}")
        
        # 3. 读取文件内容
        if os.path.exists(self.temp_xml_path):
            with open(self.temp_xml_path, 'rb') as f:
                xml_content = f.read()
            return xml_content
        else:
            print("错误：无法获取 XML 文件")
            return None

    def parse_bounds(self, bounds_str):
        """
        核心步骤3辅助: 解析坐标字符串 "[x1,y1][x2,y2]"
        返回: (x1, y1, x2, y2, center_x, center_y)
        """
        if not bounds_str:
            return None
        
        # 使用正则提取数字
        pattern = r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]'
        match = re.match(pattern, bounds_str)
        
        if match:
            x1, y1, x2, y2 = map(int, match.groups())
            center_x = (x1 + x2) // 2
            center_y = (y1 + y2) // 2
            return {
                "coords": (x1, y1, x2, y2),
                "center": (center_x, center_y)
            }
        return None

    def process_xml(self, xml_content):
        """
        核心步骤2 & 3: 解析 XML 并清洗数据
        """
        if not xml_content:
            return []

        # 使用 lxml 解析 (比标准库快)
        try:
            root = etree.fromstring(xml_content)
        except etree.XMLSyntaxError:
            print("XML 解析失败，可能是文件不完整")
            return []

        ui_elements = []
        uid_counter = 1 # 从 1 开始编号

        # 遍历所有节点
        for node in root.iter():
            # === 数据清洗与过滤逻辑 ===
            
            # 1. 获取基础属性
            resource_id = node.get("resource-id", "")
            text = node.get("text", "")
            content_desc = node.get("content-desc", "")
            class_name = node.get("class", "")
            bounds_str = node.get("bounds")
            
            # 2. 获取交互属性 (字符串转布尔)
            clickable = node.get("clickable") == "true"
            checkable = node.get("checkable") == "true" # 注意：xml里通常是 checkable
            long_clickable = node.get("long-clickable") == "true"
            editable = node.get("focusable") == "true" # 通常 focusable 意味着可能是输入框

            # === 过滤策略 ===
            # 我们只保留用户可能感兴趣的节点：
            # A. 可点击/可勾选/可长按
            # B. 有文字内容 (用于阅读屏幕信息)
            # C. 有描述内容 (用于图标识别)
            # D. 是输入框
            is_interactive = clickable or checkable or long_clickable or editable
            has_content = bool(text) or bool(content_desc)
            
            # 排除系统布局容器，除非它们可点击
            # 如果既不可交互，又没有内容，直接丢弃
            if not is_interactive and not has_content:
                continue

            # === 坐标计算 ===
            bounds_info = self.parse_bounds(bounds_str)
            if not bounds_info:
                continue
                
            # 排除宽高为 0 的无效节点
            x1, y1, x2, y2 = bounds_info['coords']
            if x2 - x1 <= 0 or y2 - y1 <= 0:
                continue

            # === 构建数据对象 ===
            element = {
                "id": uid_counter,
                "type": class_name.split('.')[-1], # 简化类名，如 android.widget.Button -> Button
                "text": text,
                "desc": content_desc,
                "resource_id": resource_id,
                "center_x": bounds_info['center'][0],
                "center_y": bounds_info['center'][1],
                "bounds": bounds_info['coords'],
                # 标记特殊属性，帮助 LLM 判断
                "is_clickable": clickable,
                "is_editable": editable
            }
            
            ui_elements.append(element)
            uid_counter += 1

        return ui_elements

    def generate_prompt_text(self, ui_elements):
        """
        生成给 LLM 看的文本格式 (节省 Token)
        """
        lines = []
        for e in ui_elements:
            # 优先展示有意义的文字
            content = e['text'] if e['text'] else e['desc']
            if not content:
                content = "[无文字图标]" # 标记一下，提示 LLM 需要看 resource_id
            
            # 格式化: [ID] <类型> "内容" (ID名)
            line = f"[{e['id']}] <{e['type']}> \"{content}\""
            
            # 如果有 resource_id，加上它 (通常包含如 'search', 'menu' 等关键语义)
            if e['resource_id']:
                # 只保留 id 的最后一部分，去掉包名，节省 Token
                # 如 com.tencent.mm:id/bi3 -> bi3
                simple_res_id = e['resource_id'].split('/')[-1]
                line += f" (ID: {simple_res_id})"
            
            lines.append(line)
        
        return "\n".join(lines)

# === 测试运行模块 ===
if __name__ == "__main__":
    perc = Perceptor()
    
    # 1. 获取 XML
    xml_data = perc.capture_layout()
    
    # 2. 解析
    if xml_data:
        elements = perc.process_xml(xml_data)
        
        # 3. 打印给 LLM 看的 Prompt
        print("-" * 30)
        print("发送给 LLM 的 Prompt 内容:")
        print("-" * 30)
        print(perc.generate_prompt_text(elements))
        
        # 4. 打印给 Executor 执行用的详细数据 (示例前3个)
        print("\n" + "-" * 30)
        print("供执行层使用的数据结构 (Top 3):")
        print("-" * 30)
        import json
        print(json.dumps(elements[:3], indent=2, ensure_ascii=False))