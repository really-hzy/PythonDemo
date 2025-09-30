from abc import ABC, abstractmethod

class BaseSearchProvider(ABC):
    """
    搜索提供者抽象基类

    所有搜索引擎实现都必须继承此类并实现其抽象方法
    """
    id: str
    name: str
    url: str

    def init(self):
        pass

    @abstractmethod
    async def search_images(self, query: str, num_results: int = 1) -> list[dict]:
        """
        搜索图片

        Args:
            query: 搜索关键词
            num_results: 期望返回的结果数量，默认10条

        Returns:
            图片搜索结果列表

        Raises:
            Exception: 搜索过程中的各种异常
        """
        pass

    @abstractmethod
    async def close(self):
        """
        关闭搜索提供者，释放资源

        例如关闭浏览器实例、清理临时文件等
        """
        pass

    async def __aenter__(self):
        """支持异步上下文管理器"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """退出时自动清理资源"""
        await self.close()