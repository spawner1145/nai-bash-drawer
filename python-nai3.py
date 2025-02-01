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

# key列表(用于轮询)
key_list = [
    '',
]

# 请求提示词
AAA_tags = '<wd1:artist_full=1>'

# 间隔请求时间(秒)
interval = 1 

# 定义全局变量 wildcard 文件夹的路径
WILDCARDS_DIR = '/kaggle/input/artists'

# 输出train.csv的路径
csv_path = '/kaggle/working/train.csv'

# 输出images图片压缩包的路径
zip_path = "/kaggle/working/images.zip"

# 代理
proxy = '' # 如用clash填'http://127.0.0.1:7890'

# 从第几个key开始轮询(0是第一个)
round_nai = 0

# 默认预设(其中’{}‘代表请求提示词会替换的位置)
positives = '{},rating:general, best quality, very aesthetic, absurdres'
negatives = 'blurry, lowres, error, film grain, scan artifacts, worst quality, bad quality, jpeg artifacts, very displeasing, chromatic aberration, logo, dated, signature, multiple views, gigantic breasts'

def random_str(length=32):
    valid_chars = string.ascii_letters + string.digits
    return ''.join(random.choice(valid_chars) for _ in range(length))

async def get_random_lines(file_path, count):
    async with aiofiles.open(file_path, 'r', encoding='utf-8') as file:
        lines = [line.strip() async for line in file if line.strip()]
        if not lines:
            raise ValueError(f"No content found in {file_path}")
        return [random.choice(lines) for _ in range(min(count, len(lines)))]

def add_weight(item, weight_type, a=1.0, b=None):
    if weight_type == 'fixed':
        n = round(a, 4)
    elif weight_type == 'range' and b is not None:
        n = round(random.uniform(a, b), 4)
    else:
        raise ValueError("Invalid weight type or parameters")

    if n == 1.0:
        return item
    else:
        return f"({item}:{n})"

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
                raise ValueError("Invalid weight range: start must be less than or equal to end.")

        warning_msg = f"无效的权重参数 '{weight_str}'，使用默认权重 0 到 1."
        print(warning_msg)
        return 'range', 0.0, 1.0, warning_msg
    except (ValueError, TypeError) as e:
        warning_msg = f"无效的权重参数 '{weight_str}'，使用默认权重 0 到 1. 错误信息: {e}"
        print(warning_msg)
        return 'range', 0.0, 1.0, warning_msg

async def replace_wildcards(input_string, wildcards_relative_path=''):
    pattern = re.compile(r'<(wd[^:]*):([a-zA-Z0-9_]+)(?:=([0-9]+))?>')
    wildcards_dir = os.path.join(WILDCARDS_DIR, wildcards_relative_path)
    if not os.path.isdir(wildcards_dir):
        raise NotADirectoryError(f"The directory does not exist: {wildcards_dir}")

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
                        raise ValueError("Invalid weight type")

                    replaced_items.append(replaced_item)

                replaced_str = ','.join(replaced_items)
                return replaced_str, f"{match.group(0)} -> {replaced_str}", log_entry
            except (ValueError, TypeError) as e:
                error_msg = f"Invalid number of lines or weight parameters: {e}"
                print(error_msg)
                return match.group(0), None, error_msg
            except Exception as e:
                error_msg = f"Unexpected error: {e}"
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
            combined_log = f"{log_entry}, {weight_log}"
            replacement_log.append(combined_log)
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
        available_files = []
        for entry in os.scandir(wildcards_dir):
            if entry.is_file() and entry.name.endswith('.txt'):
                available_files.append(entry.name)
        if not available_files:
            return "无wildcard"
        wildcard_strings = [f"<wd1:{os.path.splitext(f)[0]}=1>" for f in available_files]
        result_string = '\n'.join(wildcard_strings)
        return result_string
    except Exception as e:
        print("An error occurred while scanning the directory:", e)
        return "无wildcard"

async def n4(prompt, zip_file, filename):
    global round_nai
    
    # 随机选择一组分辨率
    resolutions = [
        (1024, 1024),  # 方形
        (1216, 832),   # 横向
        (832, 1216)    # 纵向
    ]
    width, height = random.choice(resolutions)
    
    url = "https://image.novelai.net"

    positive = positives
    negative = negatives
    positive = (("{}," + positive) if "{}" not in positive else positive).replace("{}", prompt) if isinstance(positive, str) else str(prompt)

    payload = {
        "input": positive,
        "model": "nai-diffusion-3",
        "action": "generate",
        "parameters": {
            "params_version": 3,
            "width": width,
            "height": height,
            "scale": 5,
            "sampler": "k_euler_ancestral",
            "steps": 23,
            "n_samples": 1,
            "ucPreset": 0,
            "qualityToggle": True,
            "sm": False,
            "sm_dyn": False,
            "dynamic_thresholding": False,
            "controlnet_strength": 1,
            "legacy": False,
            "add_original_image": True,
            "cfg_rescale": 0,
            "noise_schedule": "karras",
            "legacy_v3_extend": False,
            "skip_cfg_above_sigma": None,
            "seed": random.randint(0, 2 ** 32 - 1),
            "characterPrompts": [],
            "negative_prompt": negative,
            "reference_image_multiple": [],
            "reference_information_extracted_multiple": [],
            "reference_strength_multiple": []
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
    round_nai += 1
    list_length = len(key_list)
    if round_nai >= list_length:
        round_nai = 0
    if proxy:
        proxies = {"http://": proxy, "https://": proxy}
    else:
        proxies = None
    async with httpx.AsyncClient(timeout=1000, proxies=proxies) as client:
        response = await client.post(url=f'{url}/ai/generate-image', json=payload, headers=headers)
        response.raise_for_status()
        zip_content = response.content
        zip_file_inner = io.BytesIO(zip_content)
        with zipfile.ZipFile(zip_file_inner, 'r') as zf:
            file_names = zf.namelist()
            if not file_names:
                raise ValueError("The zip archive is empty.")
            file_name = file_names[0]
            if not file_name.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                raise ValueError("The zip archive does not contain an image file.")
            image_data = zf.read(file_name)
            zip_file.writestr(filename, image_data)
    return filename

async def nai4(tag):
    tag, log = await replace_wildcards(tag)
    filename = f"{random_str()}.png"
    #print(f"发起nai4绘画请求|prompt:{tag}")

    retries_left = 50
    while retries_left > 0:
        try:
            with zipfile.ZipFile(zip_path, 'a') as zf:
                generated_filename = await n4(tag, zf, filename)
            
            header = ['filename', 'tags']
            data = [generated_filename, tag]
            file_exists = os.path.isfile(csv_path)
            with open(csv_path, mode='a', newline='') as file:
                writer = csv.writer(file)
                if not file_exists:
                    writer.writerow(header)
                writer.writerow(data)
                
            print(f"成功写入CSV文件 | filename: {generated_filename}, tag: {tag}")
            return
        except Exception as e:
            retries_left -= 1
            #print(f"nai4报错{e}，剩余尝试次数：{retries_left}")
            if retries_left == 0:
                print(f"nai4画图失败{e}", True)

async def naiDraw4(tag = '<wd1:artist=1>'):
    #print('正在进行nai4画图')
    await nai4(tag)

async def main():
    while True:
        asyncio.create_task(naiDraw4(AAA_tags))
        await asyncio.sleep(interval)

if __name__ == "__main__":
    asyncio.run(main())
