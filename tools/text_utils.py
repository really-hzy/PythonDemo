import re

def extract_image_placeholders(report_text: str) -> dict[str, str]:
    """
    从markdown报告文本中提取所有图片占位符的关键词。
    图片格式：![图片描述](图片URL)
    例子：![洪崖洞夜景](https://upload.wikimedia.org/wikipedia/commons/thumb/6/67/Chongqing_Nightscape.jpg/640px-Chongqing_Nightscape.jpg)
    """
    # 图片描述: 图片URL
    queries = {}
    for line in report_text.split('\n'):
        # 使用正则表达式提取图片描述
        match = re.search(r'!\[(.?)\]\((.?)\)', line)
        if match:
            queries[match.group(1)] = match.group(2)
    return queries

def populate_report_with_images(report_text: str, images: dict[str, str]) -> str:
    """
    将图片信息填充回报告文本中。
    images: 原始图片URL，替换后的图片URL
    """
    # [original image, replace with new image]
    for original_url, new_url in images.items():
        report_text = report_text.replace(original_url, new_url)
    return report_text

if __name__ == "__main__":
    with open("/Users/smile/Documents/output.md", "r", encoding="utf-8") as f:
        report_text = f.read()
    # 默认全替换了，但可能只需要替换部分
    queries = extract_image_placeholders(report_text)
    print(queries)
    import sys
    sys.path.append("/Users/smile/Documents/Github/PythonDemo")
    from tools.api_clients.google_scraper import batch_search_google_images
    import asyncio
    images = asyncio.run(batch_search_google_images(list(queries.keys()), num_results_per_query=1, max_concurrency=1))
    replace_images = {}
    for query, image in images.items():
        replace_images[queries[query]] = image[0].get('url')
    report_text = populate_report_with_images(report_text, replace_images)
    print(report_text)