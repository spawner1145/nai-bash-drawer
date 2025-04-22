import json
from PIL import Image
import httpx
import random
import zipfile
from bs4 import BeautifulSoup
import io
import base64
import re
import aiofiles
import asyncio
import os
from io import BytesIO
import csv
import string

async def random_str(length=32):
    valid_chars = string.ascii_letters + string.digits
    return ''.join(random.choice(valid_chars) for _ in range(length))

async def get_random_lines(file_path, count):
    async with aiofiles.open(file_path, 'r', encoding='utf-8') as file:
        lines = [line.strip() async for line in file if line.strip()]
        if not lines:
            raise ValueError(f"文件 {file_path} 没有内容")
        return [random.choice(lines) for _ in range(min(count, len(lines)))]

def add_weight(item, weight_type, a=1.0, b=None):
    if weight_type == 'fixed':
        n = round(a, 4)
    elif weight_type == 'range' and b is not None:
        n = round(random.uniform(a, b), 4)
    else:
        raise ValueError("无效的权重类型或参数")
    return item if n == 1.0 else f"({item}:{n})"

def parse_weight_params(weight_str):
    try:
        if not weight_str:
            warning_msg = "无效的权重参数 ''，使用默认权重 0 到 1."
            print(warning_msg)
            return 'range', 0.0, 1.0, warning_msg
        weight_str = weight_str.replace('wd', '', 1)
        try:
            a = float(weight_str)
            return 'fixed', a, None, None
        except ValueError:
            pass
        if '-' in weight_str:
            a, b = map(float, weight_str.split('-'))
            if a <= b:
                return 'range', a, b, None
            else:
                raise ValueError("权重范围无效：开始值必须小于或等于结束值")
        warning_msg = f"无效的权重参数 '{weight_str}'，使用默认权重 0 到 1."
        print(warning_msg)
        return 'range', 0.0, 1.0, warning_msg
    except (ValueError, TypeError) as e:
        warning_msg = f"无效的权重参数 '{weight_str}'，使用默认权重 0 到 1. 错误: {e}"
        print(warning_msg)
        return 'range', 0.0, 1.0, warning_msg

async def replace_wildcards(input_string, wildcards_relative_path=''):
    pattern = re.compile(r'<(wd[^:]*):([a-zA-Z0-9_]+)(?:=([0-9]+))?>')
    wildcards_dir = os.path.join(WILDCARDS_DIR, wildcards_relative_path)
    if not os.path.isdir(wildcards_dir):
        raise NotADirectoryError(f"目录不存在: {wildcards_dir}")
    matches = list(pattern.finditer(input_string))
    replacement_tasks = []
    for match in matches:
        weight_part, wildcard_name, num_lines_str = match.groups()
        file_path = os.path.join(wildcards_dir, f'{wildcard_name}.txt')
        async def process_match(match, weight_part, file_path, num_lines_str=None):
            if not os.path.isfile(file_path):
                return match.group(0), None, None
            try:
                num_lines = int(num_lines_str) if num_lines_str else 1
                weight_type, a, b, log_entry = parse_weight_params(weight_part)
                selected_items = await get_random_lines(file_path, num_lines)
                replaced_items = []
                for item in selected_items:
                    if weight_type == 'fixed':
                        replaced_item = add_weight(item, 'fixed', a=a)
                    elif weight_type == 'range':
                        replaced_item = add_weight(item, 'range', a=a, b=b)
                    else:
                        raise ValueError("无效的权重类型")
                    replaced_items.append(replaced_item)
                replaced_str = ','.join(replaced_items)
                return replaced_str, f"{match.group(0)} -> {replaced_str}", log_entry
            except (ValueError, TypeError) as e:
                error_msg = f"无效的行数或权重参数: {e}"
                print(error_msg)
                return match.group(0), None, error_msg
            except Exception as e:
                error_msg = f"意外错误: {e}"
                print(error_msg)
                return match.group(0), None, error_msg
        replacement_tasks.append(process_match(match, weight_part, file_path, num_lines_str))
    replacements = await asyncio.gather(*replacement_tasks)
    parts = []
    last_end = 0
    replacement_log = []
    for i, match in enumerate(matches):
        parts.append(input_string[last_end:match.start()])
        new_str, log_entry, weight_log = replacements[i]
        if log_entry and weight_log:
            replacement_log.append(f"{log_entry}, {weight_log}")
        elif log_entry:
            replacement_log.append(log_entry)
        elif weight_log:
            replacement_log.append(weight_log)
        parts.append(new_str or match.group(0))
        last_end = match.end()
    parts.append(input_string[last_end:])
    result = ''.join(parts)
    log = '; '.join(replacement_log) if replacement_log else False
    return result, log

async def get_available_wildcards(wildcards_relative_path=''):
    wildcards_dir = os.path.join(WILDCARDS_DIR, wildcards_relative_path)
    if not os.path.isdir(wildcards_dir):
        return "无wildcard"
    try:
        available_files = [entry.name for entry in os.scandir(wildcards_dir) if entry.is_file() and entry.name.endswith('.txt')]
        if not available_files:
            return "无wildcard"
        wildcard_strings = [f"<wd1:{os.path.splitext(f)[0]}=1>" for f in available_files]
        return '\n'.join(wildcard_strings)
    except Exception as e:
        print(f"扫描目录时出错: {e}")
        return "无wildcard"

async def n4(prompt, output_type, output_dir, zip_file, filename):
    global round_nai
    resolutions = [(1024, 1024), (1216, 832), (832, 1216)]
    width, height = random.choice(resolutions)
    url = "https://image.novelai.net"
    positive = positives.format(prompt) if "{}" in positives else f"{prompt},{positives}"
    payload = {
        "input": positive,
        "model": "nai-diffusion-4-curated-preview",
        "action": "generate",
        "parameters": {
            "params_version": 3,
            "width": width,
            "height": height,
            "scale": 6,
            "sampler": "k_euler_ancestral",
            "steps": 23,
            "n_samples": 1,
            "ucPreset": 0,
            "qualityToggle": True,
            "dynamic_thresholding": False,
            "controlnet_strength": 1,
            "legacy": False,
            "add_original_image": True,
            "cfg_rescale": 0,
            "noise_schedule": "karras",
            "legacy_v3_extend": False,
            "skip_cfg_above_sigma": None,
            "use_coords": False,
            "seed": random.randint(0, 2 ** 32 - 1),
            "characterPrompts": [],
            "v4_prompt": {
                "caption": {"base_caption": positive, "char_captions": []},
                "use_coords": False,
                "use_order": True
            },
            "v4_negative_prompt": {"caption": {"base_caption": negatives, "char_captions": []}},
            "negative_prompt": negatives,
            "reference_image_multiple": [],
            "reference_information_extracted_multiple": [],
            "reference_strength_multiple": [],
            "deliberate_euler_ancestral_bug": False,
            "prefer_brownian": True
        }
    }
    headers = {
        "Authorization": f"Bearer {key_list[int(round_nai)]}",
        "accept": "*/*",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "content-type": "application/json",
        "dnt": "1",
        "origin": "https://novelai.net",
        "priority": "u=1, i",
        "referer": "https://novelai.net/",
        "sec-ch-ua": '"Not A(Brand";v="8", "Chromium";v="132", "Microsoft Edge";v="132"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 Edg/132.0.0.0",
        "x-correlation-id": "89SHW4",
        "x-initiated-at": "2025-01-27T16:40:54.521Z"
    }
    round_nai = (round_nai + 1) % len(key_list)
    proxies = {"http://": proxy, "https://": proxy} if proxy else None
    async with httpx.AsyncClient(timeout=1000, proxies=proxies) as client:
        response = await client.post(f'{url}/ai/generate-image', json=payload, headers=headers)
        response.raise_for_status()
        zip_content = response.content
        zip_file_inner = io.BytesIO(zip_content)
        with zipfile.ZipFile(zip_file_inner, 'r') as zf:
            file_names = zf.namelist()
            if not file_names:
                raise ValueError("压缩包为空")
            file_name = file_names[0]
            if not file_name.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                raise ValueError("压缩包不包含图片文件")
            image_data = zf.read(file_name)
            if output_type == 'zip':
                zip_file.writestr(filename, image_data)
            elif output_type == 'folder':
                os.makedirs(output_dir, exist_ok=True)
                with open(os.path.join(output_dir, filename), 'wb') as f:
                    f.write(image_data)
    return filename

async def nai4(tag, output_type, output_dir, zip_file):
    tag, log = await replace_wildcards(tag)
    filename = f"{await random_str()}.png"
    print(f"发起绘画请求 | prompt: {tag}")
    retries_left = 50
    while retries_left > 0:
        try:
            generated_filename = await n4(tag, output_type, output_dir, zip_file, filename)
            header = ['filename', 'tags']
            data = [generated_filename, tag]
            file_exists = os.path.isfile(csv_path)
            with open(csv_path, mode='a', newline='') as file:
                writer = csv.writer(file)
                if not file_exists:
                    writer.writerow(header)
                writer.writerow(data)
            print(f"成功写入CSV | filename: {generated_filename}, tag: {tag}")
            return
        except Exception as e:
            retries_left -= 1
            if retries_left == 0:
                print(f"绘画失败: {e}")

async def main():
    if OUTPUT_TYPE == 'folder' and not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR, exist_ok=True)
    zip_file = zipfile.ZipFile(zip_path, 'a') if OUTPUT_TYPE == 'zip' else None
    try:
        for _ in range(NUM_IMAGES):
            await nai4(AAA_TAGS, OUTPUT_TYPE, OUTPUT_DIR, zip_file)
            await asyncio.sleep(INTERVAL)
    finally:
        if zip_file:
            zip_file.close()

# ==================== 可配置参数 ====================
# API密钥列表（用于轮询）
KEY_LIST = ['']  # 请填入你的NovelAI API密钥

# 请求提示词
AAA_TAGS = '<wd1:artist_full=1>'  # 提示词模板，可使用wildcard

# 每次请求的间隔时间（秒）
INTERVAL = 1

# wildcard文件夹路径
WILDCARDS_DIR = '/kaggle/input/artists'

# 输出train.csv的路径
CSV_PATH = '/kaggle/working/train.csv'

# 输出类型：'zip' 表示输出到压缩包，'folder' 表示输出到文件夹
OUTPUT_TYPE = 'zip'  # 可选值：'zip' 或 'folder'

# 如果 OUTPUT_TYPE 为 'zip'，图片将保存到此压缩包
ZIP_PATH = '/kaggle/working/images.zip'

# 如果 OUTPUT_TYPE 为 'folder'，图片将保存到此文件夹
OUTPUT_DIR = '/kaggle/working/images'

# 生成的图片数量
NUM_IMAGES = 1  # 设置生成图片的数量

# 代理设置（如果需要）
PROXY = ''  # 例如：'http://127.0.0.1:7890'，不需要则留空

# 从第几个key开始轮询（0是第一个）
ROUND_NAI = 0

# 正向提示词模板（{}会被提示词替换）
POSITIVES = '{},rating:general, best quality, very aesthetic, absurdres'

# 负向提示词
NEGATIVES = 'blurry, lowres, error, film grain, scan artifacts, worst quality, bad quality, jpeg artifacts, very displeasing, chromatic aberration, logo, dated, signature, multiple views, gigantic breasts'
# ================================================

if __name__ == "__main__":
    asyncio.run(main())
