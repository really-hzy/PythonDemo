import httpx

async def search_wikimedia_for_image(query: str, num_results: int = 1) -> list[dict]:
    """
    一个专用的API调用函数，用于在维基共享资源中搜索图片。
    num_results: 搜索结果数量
    return: 图片URL
    """
    API_ENDPOINT = "https://commons.wikimedia.org/w/api.php"
    search_params = {
        "action": "query", "format": "json", "list": "search",
        "srsearch": query, "srnamespace": "6", "srlimit": str(num_results)
    }

    try:
        async with httpx.AsyncClient() as client:
            search_response = await client.get(API_ENDPOINT, params=search_params)
            search_response.raise_for_status()
            search_data = search_response.json()
            if not search_data.get("query", {}).get("search"):
                return []
            page_titles = [result["title"] for result in search_data["query"]["search"]]
            info_params = {
                "action": "query", "format": "json", "titles": "|".join(page_titles),
                "prop": "imageinfo", "iiprop": "url|extmetadata"
            }
            info_response = await client.get(API_ENDPOINT, params=info_params)
            info_response.raise_for_status()
            info_data = info_response.json()

            page_ids = list(info_data["query"]["pages"].keys())
            page_details = []
            for page_id in page_ids:
                page_details.append(info_data["query"]["pages"][page_id]["imageinfo"][0])
            return [{"url": page_detail.get("url")} for page_detail in page_details]
    except Exception as e:
        print(f"Failed to search for image '{query}': {e}")
        return []

if __name__ == "__main__":
    import asyncio
    print(asyncio.run(search_wikimedia_for_image("Hongya Cave", 2)))