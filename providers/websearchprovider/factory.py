"""
搜索提供者工厂模块
提供统一的搜索引擎创建接口，支持多种搜索引擎的注册和实例化
"""
from typing import Dict, Type, Optional
from providers.websearchprovider.base_provider import BaseSearchProvider
from providers.websearchprovider.google_provider import GoogleSearchProvider
from providers.websearchprovider.search_window import SearchWindow
class SearchProviderFactory:
    """
    搜索提供者工厂类

    使用工厂模式管理不同的搜索引擎提供者
    """

    # 注册的搜索提供者映射表
    _providers: Dict[str, Type[BaseSearchProvider]] = {
        'google': GoogleSearchProvider,
        # 未来可以扩展更多搜索引擎
        # 'bing': BingSearchProvider,
        # 'duckduckgo': DuckDuckGoSearchProvider,
    }

    @classmethod
    def create_provider(
        cls, 
        provider_type: str = 'google',
        search_window: Optional[SearchWindow] = None,
        **kwargs
    ) -> BaseSearchProvider:
        """
        创建搜索提供者实例

        Args:
            provider_type: 搜索引擎类型，默认 'google'
                支持的类型：'google'
            search_window: 可选的浏览器窗口管理器实例（页面池）。
                如果提供，多个 provider 可以共享同一个浏览器实例，实现并发搜索
            **kwargs: 传递给具体提供者的初始化参数
                例如 headless=True, timeout=30000

        Returns:
            搜索提供者实例

        Raises:
            ValueError: 当指定的提供者类型不存在时

        Examples:
            # 基础用法
            provider = SearchProviderFactory.create_provider('google')

            # 自定义配置
            provider = SearchProviderFactory.create_provider(
                            'google', 
                            headless=False, 
                            timeout=60000
                        )

            # 共享浏览器窗口（并发搜索）
            async with SearchWindow(max_pages=3) as window:
            provider = SearchProviderFactory.create_provider('google', search_window=window)    # 支持并发搜索
        """
        provider_type = provider_type.lower()

        if provider_type not in cls._providers:
            available = ', '.join(cls._providers.keys())
            raise ValueError(
                f"unsupported provider type: {provider_type}. "
                f"available types: {available}"
            )

        provider_class = cls._providers[provider_type]

        # 如果提供了 search_window，传递给 provider
        if search_window is not None:
            kwargs['search_window'] = search_window

        return provider_class(**kwargs)

    @classmethod
    def register_provider(
        cls, 
        name: str, 
        provider_class: Type[BaseSearchProvider]
    ):
        """
        注册新的搜索提供者

        Args:
            name: 提供者名称（小写）
            provider_class: 提供者类，必须继承 BaseSearchProvider

        Raises:
            TypeError: 当提供的类不是 BaseSearchProvider 的子类时

        Examples:
            class MySearchProvider(BaseSearchProvider):
                pass
            SearchProviderFactory.register_provider('mysearch', MySearchProvider)
        """
        if not issubclass(provider_class, BaseSearchProvider):
            raise TypeError(
                f"{provider_class.name} must inherit BaseSearchProvider"
            )

        cls._providers[name.lower()] = provider_class

    @classmethod
    def get_available_providers(cls) -> list[str]:
        """
        获取所有可用的搜索提供者列表

        Returns:
            可用提供者名称列表
        """
        return list(cls._providers.keys()) 