"""
Google 图片搜索提供者

使用 Playwright 无头浏览器实现动态内容加载和数据提取
"""
import asyncio
import re
from typing import Optional
from playwright.async_api import Response
from providers.websearchprovider.base_provider import BaseSearchProvider
from providers.websearchprovider.search_window import SearchWindow


class GoogleSearchProvider(BaseSearchProvider):
    """
    Google 图片搜索提供者实现
    
    使用 Playwright 启动无头浏览器访问 Google 图片搜索，
    通过监听网络请求或解析页面 DOM 来提取图片数据
    """
    
    def __init__(
        self, 
        search_window: Optional[SearchWindow] = None,
        headless: bool = True, 
        timeout: int = 30000
    ):
        """
        初始化 Google 搜索提供者
        
        Args:
            search_window: 浏览器窗口管理器实例。如果为 None，将自动创建临时实例（向后兼容）
            headless: 当 search_window 为 None 时使用的无头模式配置，默认 True
            timeout: 页面操作超时时间（毫秒），默认 30 秒
        """
        self.search_window = search_window
        self._own_window = search_window is None  # 标记是否自己创建窗口
        self.headless = headless
        self.timeout = timeout
        
        # 如果没有提供 search_window，创建临时实例（向后兼容）
        if self._own_window:
            self.search_window = SearchWindow(headless=headless, timeout=timeout)
    
    async def _handle_route(self, route):
        """
        处理路由请求，拦截不必要的资源加载以提升性能
        """
        # 阻止加载字体、样式表等不必要的资源
        if route.request.resource_type in ['font', 'stylesheet']:
            await route.abort()
        else:
            await route.continue_()
    
    async def search_images(self, query: str, num_results: int = 10) -> list[dict]:
        """
        搜索 Google 图片
        
        Args:
            query: 搜索关键词
            num_results: 期望返回的结果数量
            
        Returns:
            图片搜索结果列表
        """
        # 使用局部变量而不是实例变量，避免并发时数据混乱
        image_data_list: list[dict] = []
        
        # 使用上下文管理器自动获取和归还页面
        async with self.search_window.get_page() as page:
            # 定义局部闭包函数处理响应，访问局部变量
            async def handle_response(response: Response):
                """处理网络响应，提取图片数据"""
                try:
                    if '/search?' in response.url and response.status == 200:
                        text = await response.text()
                        # 从响应中提取图片数据
                        self._extract_image_data_from_text(text, image_data_list)
                except Exception:
                    pass  # 忽略解析错误
            
            # 定义局部闭包函数提取 DOM 数据
            async def extract_from_dom():
                """从页面 DOM 中提取图片数据（备用方案）"""
                try:
                    await page.wait_for_selector('img[data-src], img[src]', timeout=5000)
                    
                    images = await page.eval_on_selector_all(
                        'img',
                        '''(elements) => elements.map(img => ({
                            url: img.src || img.dataset.src || '',
                            thumbnail_url: img.src || img.dataset.src || '',
                            title: img.alt || '',
                            width: img.naturalWidth || 0,
                            height: img.naturalHeight || 0
                        }))'''
                    )
                    
                    for img in images:
                        url = img.get('url', '')
                        if url and url.startswith('http') and 'gstatic.com' not in url:
                            image_data_list.append(img)
                            
                except Exception as e:
                    print(f"从 DOM 提取图片时出错: {e}")
            
            try:
                page.set_default_timeout(self.timeout)
                
                # 设置请求拦截
                await page.route('**/*', self._handle_route)
                
                # 构建搜索URL
                search_url = f"https://www.google.com/search?q={query}&tbm=isch"
                
                # 监听响应以捕获图片数据
                page.on('response', handle_response)
                
                try:
                    # 访问搜索页面
                    await page.goto(search_url, wait_until='networkidle')
                    
                    # 等待图片加载
                    await page.wait_for_timeout(2000)
                    
                    # 如果没有从网络请求中获取到数据，尝试解析页面
                    if not image_data_list:
                        await extract_from_dom()
                    
                    # 转换为标准格式并返回
                    results = self._parse_results(image_data_list, num_results)
                    return results
                    
                finally:
                    # 移除事件监听器，避免影响下次使用该页面
                    try:
                        page.remove_listener('response', handle_response)
                    except Exception:
                        pass  # 忽略移除失败
                    
            except Exception as e:
                print(f"搜索图片时出错: {e}")
                raise
            # 页面会被自动归还到池中
    
    def _extract_image_data_from_text(self, text: str, image_data_list: list[dict]):
        """
        从响应文本中提取图片数据
        
        Args:
            text: 响应文本内容
            image_data_list: 用于存储图片数据的列表
        """
        try:
            # Google 在页面中嵌入了 JSON 数据，通常在 AF_initDataCallback 中
            # 使用正则表达式提取这些数据
            pattern = r'\["(https?://[^"]+\.(?:jpg|jpeg|png|gif|webp)[^"]*)"'
            matches = re.findall(pattern, text, re.IGNORECASE)
            
            for url in matches:
                # 过滤掉 Google 自己的图标和小图
                if 'gstatic.com' not in url and len(url) > 50:
                    image_data_list.append({
                        'url': url,
                        'thumbnail_url': url,
                        'title': '',
                        'source_url': ''
                    })
                    
        except Exception as e:
            print(f"从文本提取图片数据时出错: {e}")
    
    def _parse_results(self, image_data_list: list[dict], num_results: int) -> list[dict]:
        """
        解析并格式化搜索结果
        
        Args:
            image_data_list: 原始图片数据列表
            num_results: 需要返回的结果数量
            
        Returns:
            标准化的图片搜索结果列表
        """
        results = []
        seen_urls = set()
        
        for item in image_data_list:
            url = item.get('url', '')
            
            # 去重
            if url and url not in seen_urls:
                seen_urls.add(url)
                
                result = dict(
                    url=url,
                    thumbnail_url=item.get('thumbnail_url'),
                    title=item.get('title', ''),
                    source_url=item.get('source_url'),
                    width=item.get('width'),
                    height=item.get('height')
                )
                results.append(result)
                
                # 达到目标数量则停止
                if len(results) >= num_results:
                    break
        
        return results
    
    async def close(self):
        """关闭资源"""
        # 只有自己创建的 window 才关闭
        if self._own_window and self.search_window:
            await self.search_window.close()