"""
浏览器窗口管理器 - 页面池架构

统一管理 Playwright 浏览器实例和页面池，支持并发搜索和资源复用
"""
import asyncio
from typing import Optional, List
from contextlib import asynccontextmanager
from playwright.async_api import async_playwright, Browser, Page, Playwright


class SearchWindow:
    """
    浏览器窗口管理器（页面池架构）
    
    使用页面池技术实现真正的并发搜索，显著提升批量搜索性能。
    使用 Semaphore 控制并发，避免锁竞争和死锁问题。
    
    特性：
    - 页面池管理：维护可复用的页面实例池
    - 并发控制：通过 Semaphore 限制最大并发数（无死锁风险）
    - 自动扩展：根据需求自动创建页面（不超过 max_pages）
    - 资源回收：自动清理和重置页面状态
    - 线程安全：使用队列和信号量保证并发安全
    
    使用示例：
        # 方式一：上下文管理器（推荐）
        async with SearchWindow(max_pages=3) as window:
            async with window.get_page() as page:
                # 使用 page 进行操作
        
        # 方式二：手动管理
        window = SearchWindow(max_pages=3)
        page = await window.acquire_page()
        try:
            # 使用 page
            pass
        finally:
            await window.release_page(page)
            await window.close()
    """
    
    def __init__(
        self, 
        headless: bool = True, 
        timeout: int = 30000,
        min_pages: int = 1,
        max_pages: int = 5
    ):
        """
        初始化浏览器窗口管理器
        
        Args:
            headless: 是否使用无头模式，默认 True
            timeout: 页面操作默认超时时间（毫秒），默认 30 秒
            min_pages: 最小保持的页面数量，默认 1
            max_pages: 最大页面数量（并发上限），默认 5，建议 2-5 之间
        """
        if min_pages < 1:
            raise ValueError("min_pages 必须至少为 1")
        if max_pages < min_pages:
            raise ValueError("max_pages 必须大于等于 min_pages")
        
        self.headless = headless
        self.timeout = timeout
        self.min_pages = min_pages
        self.max_pages = max_pages
        
        # 资源实例
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        
        # 页面池
        self._available_pages: asyncio.Queue[Page] = asyncio.Queue()
        self._all_pages: List[Page] = []
        
        # 并发控制：使用 Semaphore 代替手动计数和锁
        self._semaphore = asyncio.Semaphore(max_pages)
        
        # 浏览器初始化锁（只在初始化浏览器时使用，避免重复创建）
        self._browser_lock = asyncio.Lock()
        self._initialized = False
        
    async def _ensure_browser_launched(self):
        """
        确保浏览器已启动（懒加载）
        
        使用锁保证线程安全，避免重复创建浏览器实例
        """
        if self.browser is not None:
            return
            
        async with self._browser_lock:
            # 双重检查
            if self.browser is not None:
                return
            
            # 启动 Playwright
            self.playwright = await async_playwright().start()
            
            # 启动浏览器
            self.browser = await self.playwright.chromium.launch(
                headless=self.headless,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                ]
            )
    
    async def _create_page(self) -> Page:
        """
        创建新的页面实例（私有方法）
        
        Returns:
            新创建的页面实例
        """
        # 确保浏览器已启动
        await self._ensure_browser_launched()
        
        # 创建上下文
        context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        
        # 创建页面
        page = await context.new_page()
        page.set_default_timeout(self.timeout)
        
        # 添加到所有页面列表
        self._all_pages.append(page)
        
        return page
    
    async def _initialize_pages(self):
        """
        初始化最小数量的页面
        
        在首次使用时调用，预创建 min_pages 数量的页面
        """
        if self._initialized:
            return

        # 创建最小数量的页面
        for _ in range(self.min_pages):
            page = await self._create_page()
            await self._available_pages.put(page)
        
        self._initialized = True
    
    async def acquire_page(self) -> Page:
        """
        从池中获取可用页面
        
        使用 Semaphore 控制并发数，逻辑简洁无死锁风险：
        1. 获取信号量（如果已达到 max_pages，会自动等待）
        2. 尝试从队列获取可用页面
        3. 如果队列为空，创建新页面
        
        Returns:
            可用的页面实例
            
        Raises:
            Exception: 浏览器启动或页面创建失败
        """
        # 确保已初始化
        await self._initialize_pages()
        
        # 获取信号量（限制并发数）
        await self._semaphore.acquire()
        
        try:
            # 尝试从队列获取可用页面（非阻塞）
            page = self._available_pages.get_nowait()
            return page
        except asyncio.QueueEmpty:
            # 队列为空，创建新页面
            # Semaphore 已经保证不会超过 max_pages
            try:
                page = await self._create_page()
                return page
            except Exception as e:
                # 创建失败，释放信号量
                self._semaphore.release()
                raise
    
    async def release_page(self, page: Page):
        """
        归还页面到池中
        
        归还前会重置页面状态，清空 cookies 和 storage
        
        Args:
            page: 要归还的页面实例
        """
        if page is None:
            return
        
        try:
            # 重置页面状态
            await self._reset_page(page)
            
            # 归还到队列
            await self._available_pages.put(page)
            
        except Exception as e:
            # 如果重置失败，从池中移除该页面
            print(f"归还页面时出错，将从池中移除: {e}")
            if page in self._all_pages:
                self._all_pages.remove(page)
            
            # 尝试关闭问题页面
            try:
                await page.close()
            except Exception:
                pass
        finally:
            # 无论成功或失败，都要释放信号量
            self._semaphore.release()
    
    async def _reset_page(self, page: Page):
        """
        重置页面状态（私有方法）
        
        清空 cookies、localStorage、sessionStorage，
        为下一次搜索准备干净的环境
        
        Args:
            page: 要重置的页面实例
        """
        try:
            # 清空存储
            await page.evaluate("""() => {
                try {
                    localStorage.clear();
                    sessionStorage.clear();
                } catch(e) {}
            }""")
            
            # 清空 cookies
            context = page.context
            await context.clear_cookies()
            
        except Exception as e:
            # 如果页面已经关闭或出现其他问题，抛出异常
            raise Exception(f"重置页面状态失败: {e}")
    
    @asynccontextmanager
    async def get_page(self):
        """
        上下文管理器方式获取页面（推荐使用）
        
        自动获取和归还页面，确保资源正确回收
        
        Yields:
            可用的页面实例
            
        Examples:
            >>> async with window.get_page() as page:
            ...     await page.goto("https://example.com")
        """
        page = await self.acquire_page()
        try:
            yield page
        finally:
            await self.release_page(page)
    
    async def close(self):
        """
        关闭所有资源并释放
        
        关闭顺序：所有页面 -> 浏览器 -> Playwright
        """
        # 关闭所有页面
        for page in self._all_pages:
            try:
                await page.close()
            except Exception:
                pass  # 忽略关闭错误
        
        self._all_pages.clear()
        
        # 清空队列
        while not self._available_pages.empty():
            try:
                self._available_pages.get_nowait()
            except asyncio.QueueEmpty:
                break
        
        # 关闭浏览器
        if self.browser is not None:
            try:
                await self.browser.close()
            except Exception:
                pass  # 忽略关闭错误
            finally:
                self.browser = None
        
        # 停止 Playwright
        if self.playwright is not None:
            try:
                await self.playwright.stop()
            except Exception:
                pass  # 忽略关闭错误
            finally:
                self.playwright = None
        
        self._initialized = False
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出，自动清理资源"""
        await self.close()