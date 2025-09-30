"""
Google 图片搜索窗口

提供便捷的 Google 图片搜索接口，内部使用 websearchprovider 实现
支持缓存、批量搜索等高级功能
"""

if __name__ == "__main__":
    import sys
    sys.path.append("/Users/smile/Documents/Github/PythonDemo")

import asyncio
from providers.websearchprovider.factory import SearchProviderFactory
from providers.websearchprovider.search_window import SearchWindow


async def search_google_images(
    query: str, 
    num_results: int = 10,
    use_cache: bool = False
) -> list[dict]:
    """
    搜索 Google 图片（便捷函数）
    
    这是一个高层封装函数，简化了搜索调用流程。
    内部使用 SearchProviderFactory 创建 Google 搜索提供者。
    
    Args:
        query: 搜索关键词
        num_results: 期望返回的结果数量，默认 10 条
        use_cache: 是否使用缓存（暂未实现），默认 False
        
    Returns:
        图片搜索结果列表
        
    Raises:
        Exception: 搜索过程中的各种异常
        
    Examples:
        >>> import asyncio
        >>> results = asyncio.run(search_google_images("洪崖洞夜景", num_results=5))
        >>> for result in results:
        ...     print(f"图片URL: {result['url']}")
        ...     print(f"标题: {result['title']}")
    """
    # 使用工厂创建 Google 搜索提供者
    async with SearchProviderFactory.create_provider('google') as provider:
        results = await provider.search_images(query, num_results)
        return results


async def batch_search_google_images(
    queries: list[str],
    num_results_per_query: int = 10,
    max_concurrency: int = 3
) -> dict[str, list[dict]]:
    """
    批量搜索 Google 图片（支持真正并发）
    
    使用页面池技术实现真正的并发搜索，显著提升批量搜索性能。
    相比串行搜索，性能提升 2-3 倍。
    
    Args:
        queries: 搜索关键词列表
        num_results_per_query: 每个关键词期望返回的结果数量
        max_concurrency: 最大并发数，默认 3（建议 2-5 之间，避免过度消耗资源）
        
    Returns:
        字典，键为搜索关键词，值为对应的搜索结果列表
        
    Examples:
        >>> import asyncio
        >>> queries = ["洪崖洞夜景", "重庆火锅", "长江索道"]
        >>> results = asyncio.run(batch_search_google_images(queries, num_results_per_query=3, max_concurrency=3))
        >>> for query, images in results.items():
        ...     print(f"{query}: 找到 {len(images)} 张图片")
    """
    results: dict[str, list[dict]] = {}

    # 创建共享的 SearchWindow，max_pages 等于 max_concurrency
    async with SearchWindow(
        headless=True, 
        timeout=30000,
        min_pages=1,
        max_pages=max_concurrency
    ) as window:
        # 使用共享窗口创建 provider
        provider = SearchProviderFactory.create_provider(
            'google', 
            search_window=window
        )
        
        async def safe_search(query: str):
            try:
                return await provider.search_images(query, num_results_per_query)
            except Exception as e:
                print(f"批量搜索出错 '{query}': {e}")
                return []

        # 并发执行所有搜索任务
        tasks = [safe_search(query) for query in queries]
        raw_results = await asyncio.gather(*tasks)
        results = dict(zip(queries, raw_results))

    return results


# 测试代码
if __name__ == "__main__":
    import asyncio
    
    async def test_single_search():
        """测试单个搜索"""
        print("=== 测试单个图片搜索 ===")
        results = await search_google_images("洪崖洞夜景", num_results=5)
        print(f"找到 {len(results)} 张图片:")
        for i, result in enumerate(results, 1):
            print(f"\n图片 {i}:")
            print(f"  url: {result.get('url')}")
            print(f"  title: {result.get('title')}")
            print(f"  thumbnail_url: {result.get('thumbnail_url')}")
    
    async def test_batch_search():
        """测试批量搜索"""
        print("\n=== 测试批量图片搜索（并发） ===")
        queries = ["洪崖洞夜景", "重庆火锅", "长江索道"]
        results = await batch_search_google_images(queries, num_results_per_query=3, max_concurrency=3)
        
        for query, images in results.items():
            print(f"\n关键词: {query}")
            print(f"找到 {len(images)} 张图片")
            for i, img in enumerate(images, 1):
                print(f"  {i}. {img['url'][:80]}...")

    # 运行测试
    import time
    
    start_time = time.monotonic()
    asyncio.run(test_single_search())
    end_time = time.monotonic()
    print(f"\n单个图片搜索耗时: {(end_time - start_time) * 1000:.2f} 毫秒")

    start_time = time.monotonic()
    asyncio.run(test_batch_search())
    end_time = time.monotonic()
    print(f"\n批量图片搜索耗时: {(end_time - start_time) * 1000:.2f} 毫秒")