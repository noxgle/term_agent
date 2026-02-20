"""
WebSearchAgent - Sub-agent for web search and content extraction.

Supports two search engines:
- DuckDuckGo (default, no API key required)
- SearxNG (self-hosted instance required)

Features internal loop for multi-source data aggregation.
Async implementation for parallel content fetching.
"""

import os
import re
import json
import time
import asyncio
from datetime import datetime
from typing import Optional, Dict, List, Any
from urllib.parse import urljoin, urlparse

# Web search and scraping
try:
    from ddgs import DDGS
    DUCKDUCKGO_AVAILABLE = True
except ImportError:
    try:
        from duckduckgo_search import DDGS  # Fallback for older package name
        DUCKDUCKGO_AVAILABLE = True
    except ImportError:
        DUCKDUCKGO_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False


class WebSearchAgent:
    """
    Sub-agent for autonomous web search and content extraction.
    
    Features:
    - Internal loop for iterative search refinement
    - Multi-source data aggregation
    - Async parallel content extraction from web pages
    - AI-powered evaluation of search completeness
    
    Supported engines:
    - DuckDuckGo (duckduckgo-search library)
    - SearxNG (self-hosted instance)
    """
    
    # Default configuration
    DEFAULT_CONFIG = {
        'engine': 'duckduckgo',
        'searxng_url': 'http://localhost:8888',
        'max_iterations': 5,
        'max_sources': 5,
        'min_confidence': 0.7,
        'timeout': 30,
        'extract_content': True,
        'max_content_length': 10000,
        'user_agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'max_concurrent_fetches': 5,  # Limit concurrent async requests
    }
    
    def __init__(self, ai_handler=None, logger=None, config: Dict[str, Any] = None):
        """
        Initialize WebSearchAgent.
        
        Args:
            ai_handler: AI communication handler for intelligent decisions
            logger: Logger instance
            config: Configuration dictionary (overrides defaults and .env)
        """
        self.ai_handler = ai_handler
        self.logger = logger or self._create_dummy_logger()
        
        # Load configuration from .env and merge with defaults
        self.config = self.DEFAULT_CONFIG.copy()
        self._load_env_config()
        
        if config:
            self.config.update(config)
        
        # Validate dependencies
        self._validate_dependencies()
        
        # Track aggregated results
        self.aggregated_sources: List[Dict] = []
        self.iteration_count = 0
        
    def _create_dummy_logger(self):
        """Create fallback logger if none provided."""
        class DummyLogger:
            def debug(self, *args, **kwargs): pass
            def info(self, *args, **kwargs): pass
            def warning(self, *args, **kwargs): pass
            def error(self, *args, **kwargs): pass
        return DummyLogger()
    
    def _load_env_config(self):
        """Load configuration from environment variables."""
        env_mappings = {
            'WEB_SEARCH_ENGINE': 'engine',
            'SEARXNG_URL': 'searxng_url',
            'WEB_SEARCH_MAX_ITERATIONS': ('max_iterations', int),
            'WEB_SEARCH_MAX_SOURCES': ('max_sources', int),
            'WEB_SEARCH_MIN_CONFIDENCE': ('min_confidence', float),
            'WEB_SEARCH_TIMEOUT': ('timeout', int),
            'WEB_SEARCH_EXTRACT_CONTENT': ('extract_content', lambda x: x.lower() == 'true'),
            'WEB_SEARCH_MAX_CONTENT_LENGTH': ('max_content_length', int),
            'WEB_SEARCH_USER_AGENT': 'user_agent',
            'WEB_SEARCH_MAX_CONCURRENT_FETCHES': ('max_concurrent_fetches', int),
        }
        
        for env_var, config_key in env_mappings.items():
            value = os.getenv(env_var)
            if value:
                if isinstance(config_key, tuple):
                    key, converter = config_key
                    try:
                        self.config[key] = converter(value)
                    except (ValueError, TypeError):
                        self.logger.warning(f"Invalid value for {env_var}: {value}")
                else:
                    self.config[config_key] = value
    
    def _validate_dependencies(self):
        """Check if required dependencies are available."""
        if self.config['engine'] == 'duckduckgo' and not DUCKDUCKGO_AVAILABLE:
            raise ImportError("duckduckgo-search is required for DuckDuckGo engine. Install with: pip install duckduckgo-search")
        
        if not REQUESTS_AVAILABLE:
            raise ImportError("requests is required for web search. Install with: pip install requests")
        
        if self.config['extract_content'] and not BS4_AVAILABLE:
            self.logger.warning("beautifulsoup4 not available. Content extraction will be limited.")
            self.config['extract_content'] = False
        
        if not AIOHTTP_AVAILABLE:
            self.logger.warning("aiohttp not available. Falling back to synchronous requests.")
    
    def execute(self, query: str, engine: str = None, max_sources: int = None,
                deep_search: bool = True) -> Dict[str, Any]:
        """
        Execute web search (synchronous wrapper for async implementation).
        
        Args:
            query: Search query
            engine: Search engine to use ('duckduckgo' or 'searxng')
            max_sources: Maximum number of sources per iteration
            deep_search: Enable internal loop for multi-source aggregation
            
        Returns:
            Dictionary with search results
        """
        try:
            # Try to run in existing event loop if available
            loop = asyncio.get_running_loop()
            # If we're already in an async context, create a task
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    self.execute_async(query, engine, max_sources, deep_search)
                )
                return future.result()
        except RuntimeError:
            # No running loop, create new one
            return asyncio.run(self.execute_async(query, engine, max_sources, deep_search))
    
    async def execute_async(self, query: str, engine: str = None, max_sources: int = None,
                            deep_search: bool = True) -> Dict[str, Any]:
        """
        Execute web search with internal loop for data aggregation (async implementation).
        
        Args:
            query: Search query
            engine: Search engine to use ('duckduckgo' or 'searxng')
            max_sources: Maximum number of sources per iteration
            deep_search: Enable internal loop for multi-source aggregation
            
        Returns:
            Dictionary with search results:
            {
                'success': bool,
                'summary': str,
                'sources': [{'url', 'title', 'content', 'relevance'}, ...],
                'confidence': float,
                'iterations_used': int,
                'follow_up_suggestions': list
            }
        """
        # Reset state
        self.aggregated_sources = []
        self.iteration_count = 0
        
        # Use provided parameters or config defaults
        engine = engine or self.config['engine']
        max_sources = max_sources or self.config['max_sources']
        max_iterations = self.config['max_iterations']
        
        current_query = query
        
        self.logger.info(f"Starting async web search agent for query: {query}")
        
        # Internal loop
        while self.iteration_count < max_iterations:
            self.iteration_count += 1
            self.logger.info(f"Iteration {self.iteration_count}/{max_iterations}")
            
            # Step 1: Search
            try:
                search_results = self._search(current_query, engine, max_sources)
            except Exception as e:
                self.logger.error(f"Search failed: {e}")
                return self._build_response(success=False, error=str(e))
            
            # Step 2: Extract content from new sources (ASYNC PARALLEL)
            new_sources = 0
            urls_to_fetch = []
            results_to_process = []
            
            for result in search_results:
                url = result.get('url', '')
                
                # Skip already processed URLs
                if any(s['url'] == url for s in self.aggregated_sources):
                    continue
                
                urls_to_fetch.append(url)
                results_to_process.append(result)
            
            # Parallel content extraction
            if urls_to_fetch:
                contents = await self._extract_content_batch_async(urls_to_fetch)
                
                for result, content in zip(results_to_process, contents):
                    url = result.get('url', '')
                    
                    # Calculate relevance
                    relevance = self._calculate_relevance(content, query)
                    
                    self.aggregated_sources.append({
                        'url': url,
                        'title': result.get('title', ''),
                        'snippet': result.get('snippet', ''),
                        'content': content,
                        'relevance': relevance,
                        'iteration': self.iteration_count
                    })
                    new_sources += 1
            
            self.logger.info(f"Found {new_sources} new sources in iteration {self.iteration_count}")
            
            # Step 3: Evaluate if more data is needed (only if deep_search enabled)
            if not deep_search:
                break
            
            if self.iteration_count < max_iterations:
                need_more = self._evaluate_need_more_data(query)
                
                if not need_more['continue']:
                    self.logger.info(f"Search complete: {need_more['reason']}")
                    break
                
                # Refine query for next iteration
                current_query = need_more.get('refined_query', current_query)
                self.logger.info(f"Continuing search with refined query: {current_query}")
        
        # Step 4: Synthesize results
        return self._build_response(success=True)
    
    def _search(self, query: str, engine: str, max_results: int) -> List[Dict]:
        """
        Execute search using specified engine (synchronous - DDGS library is sync).
        
        Args:
            query: Search query
            engine: 'duckduckgo' or 'searxng'
            max_results: Maximum number of results
            
        Returns:
            List of search results
        """
        if engine == 'duckduckgo':
            return self._search_duckduckgo(query, max_results)
        elif engine == 'searxng':
            return self._search_searxng(query, max_results)
        else:
            raise ValueError(f"Unsupported search engine: {engine}")
    
    def _search_duckduckgo(self, query: str, max_results: int) -> List[Dict]:
        """
        Search using DuckDuckGo (duckduckgo-search library).
        """
        results = []
        
        try:
            with DDGS() as ddgs:
                search_gen = ddgs.text(
                    query,
                    max_results=max_results,
                    timeout=self.config['timeout']
                )
                
                for result in search_gen:
                    results.append({
                        'url': result.get('href', ''),
                        'title': result.get('title', ''),
                        'snippet': result.get('body', ''),
                    })
                    
        except Exception as e:
            self.logger.error(f"DuckDuckGo search error: {e}")
            raise
        
        return results
    
    def _search_searxng(self, query: str, max_results: int) -> List[Dict]:
        """
        Search using SearxNG self-hosted instance.
        """
        searxng_url = self.config['searxng_url']
        
        # SearxNG search endpoint
        search_url = f"{searxng_url}/search"
        
        params = {
            'q': query,
            'format': 'json',
            'engines': 'google,bing,duckduckgo',  # Can be customized
        }
        
        headers = {
            'User-Agent': self.config['user_agent'],
            'Accept': 'application/json',
        }
        
        try:
            response = requests.get(
                search_url,
                params=params,
                headers=headers,
                timeout=self.config['timeout']
            )
            response.raise_for_status()
            
            data = response.json()
            results = []
            
            for result in data.get('results', [])[:max_results]:
                results.append({
                    'url': result.get('url', ''),
                    'title': result.get('title', ''),
                    'snippet': result.get('content', ''),
                })
                
        except Exception as e:
            self.logger.error(f"SearxNG search error: {e}")
            raise
        
        return results
    
    async def _extract_content_batch_async(self, urls: List[str]) -> List[str]:
        """
        Extract content from multiple URLs in parallel using aiohttp.
        
        Args:
            urls: List of URLs to extract content from
            
        Returns:
            List of extracted text contents (same order as urls)
        """
        if not AIOHTTP_AVAILABLE:
            # Fallback to synchronous
            return [self._extract_content(url) for url in urls]
        
        # Limit concurrent requests using semaphore
        semaphore = asyncio.Semaphore(self.config['max_concurrent_fetches'])
        
        async def fetch_with_semaphore(url: str, session: aiohttp.ClientSession) -> str:
            async with semaphore:
                return await self._extract_content_async(url, session)
        
        timeout = aiohttp.ClientTimeout(total=self.config['timeout'])
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            tasks = [fetch_with_semaphore(url, session) for url in urls]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Handle exceptions - return empty string for failed requests
            processed_results = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    self.logger.warning(f"Failed to extract content from {urls[i]}: {result}")
                    processed_results.append("")
                else:
                    processed_results.append(result)
            
            return processed_results
    
    async def _extract_content_async(self, url: str, session: aiohttp.ClientSession) -> str:
        """
        Extract main content from a web page asynchronously.
        
        Args:
            url: URL to extract content from
            session: aiohttp ClientSession
            
        Returns:
            Extracted text content
        """
        if not BS4_AVAILABLE:
            return ""
        
        headers = {
            'User-Agent': self.config['user_agent'],
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
        
        try:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    self.logger.warning(f"HTTP {response.status} for {url}")
                    return ""
                
                html = await response.text()
                
                # Parse HTML
                soup = BeautifulSoup(html, 'lxml')
                
                # Remove unwanted elements
                for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside', 'iframe', 'noscript']):
                    element.decompose()
                
                # Try to find main content
                main_content = None
                
                # Common main content selectors
                selectors = [
                    'article',
                    '[role="main"]',
                    'main',
                    '.post-content',
                    '.article-content',
                    '.content',
                    '#content',
                    '.entry-content',
                    '.post-body',
                ]
                
                for selector in selectors:
                    main_content = soup.select_one(selector)
                    if main_content:
                        break
                
                if not main_content:
                    main_content = soup.body if soup.body else soup
                
                # Extract text
                text = main_content.get_text(separator='\n', strip=True)
                
                # Clean up text
                lines = [line.strip() for line in text.split('\n') if line.strip()]
                text = '\n'.join(lines)
                
                # Limit length
                max_len = self.config['max_content_length']
                if len(text) > max_len:
                    text = text[:max_len] + '...'
                
                return text
                
        except asyncio.TimeoutError:
            self.logger.warning(f"Timeout while extracting content from {url}")
            return ""
        except Exception as e:
            self.logger.warning(f"Content extraction failed for {url}: {e}")
            return ""
    
    def _extract_content(self, url: str) -> str:
        """
        Extract main content from a web page (synchronous fallback).
        
        Args:
            url: URL to extract content from
            
        Returns:
            Extracted text content
        """
        if not BS4_AVAILABLE:
            return ""
        
        headers = {
            'User-Agent': self.config['user_agent'],
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
        
        try:
            response = requests.get(
                url,
                headers=headers,
                timeout=self.config['timeout']
            )
            response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response.text, 'lxml')
            
            # Remove unwanted elements
            for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside', 'iframe', 'noscript']):
                element.decompose()
            
            # Try to find main content
            main_content = None
            
            # Common main content selectors
            selectors = [
                'article',
                '[role="main"]',
                'main',
                '.post-content',
                '.article-content',
                '.content',
                '#content',
                '.entry-content',
                '.post-body',
            ]
            
            for selector in selectors:
                main_content = soup.select_one(selector)
                if main_content:
                    break
            
            if not main_content:
                main_content = soup.body if soup.body else soup
            
            # Extract text
            text = main_content.get_text(separator='\n', strip=True)
            
            # Clean up text
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            text = '\n'.join(lines)
            
            # Limit length
            max_len = self.config['max_content_length']
            if len(text) > max_len:
                text = text[:max_len] + '...'
            
            return text
            
        except Exception as e:
            self.logger.warning(f"Content extraction failed for {url}: {e}")
            return ""
    
    def _calculate_relevance(self, content: str, query: str) -> float:
        """
        Calculate relevance score for content against query.
        
        Simple keyword-based relevance. If AI handler is available,
        can use AI for semantic relevance.
        
        Args:
            content: Content to evaluate
            query: Original query
            
        Returns:
            Relevance score (0.0 - 1.0)
        """
        if not content:
            return 0.0
        
        # Extract keywords from query
        query_words = set(re.findall(r'\b\w{3,}\b', query.lower()))
        
        if not query_words:
            return 0.5
        
        # Count keyword occurrences in content
        content_lower = content.lower()
        matches = sum(1 for word in query_words if word in content_lower)
        
        # Basic relevance score
        relevance = matches / len(query_words)
        
        # Boost if multiple keywords found
        if matches > 1:
            relevance = min(1.0, relevance * 1.2)
        
        return round(relevance, 2)
    
    def _evaluate_need_more_data(self, original_query: str) -> Dict[str, Any]:
        """
        Evaluate if more data is needed.
        
        If AI handler is available, uses AI for intelligent evaluation.
        Otherwise, uses simple heuristic based on confidence and source count.
        
        Args:
            original_query: Original search query
            
        Returns:
            {
                'continue': bool,
                'reason': str,
                'refined_query': str,
                'current_confidence': float
            }
        """
        current_confidence = self._calculate_overall_confidence()
        
        # If AI handler available, use AI for evaluation
        if self.ai_handler:
            return self._ai_evaluate_need_more_data(original_query, current_confidence)
        
        # Simple heuristic evaluation
        min_confidence = self.config['min_confidence']
        
        if current_confidence >= min_confidence:
            return {
                'continue': False,
                'reason': f'Confidence threshold reached ({current_confidence:.2f} >= {min_confidence})',
                'refined_query': original_query,
                'current_confidence': current_confidence
            }
        
        if len(self.aggregated_sources) >= self.config['max_sources'] * 2:
            return {
                'continue': False,
                'reason': 'Maximum sources gathered',
                'refined_query': original_query,
                'current_confidence': current_confidence
            }
        
        # Need more data - create refined query
        refined_query = self._create_refined_query(original_query)
        
        return {
            'continue': True,
            'reason': f'Confidence below threshold ({current_confidence:.2f} < {min_confidence})',
            'refined_query': refined_query,
            'current_confidence': current_confidence
        }
    
    def _ai_evaluate_need_more_data(self, original_query: str, current_confidence: float) -> Dict[str, Any]:
        """
        Use AI to evaluate if more data is needed.
        """
        # Get current date and time for context
        current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Prepare summary of current knowledge
        sources_summary = []
        for source in self.aggregated_sources:
            snippet = source.get('content', source.get('snippet', ''))[:500]
            sources_summary.append(f"- {source['title']}: {snippet}...")
        
        prompt = f"""Analyze the search results for the query: "{original_query}"

Current date and time: {current_datetime}

Current search results:
{chr(10).join(sources_summary)}

Confidence score: {current_confidence:.2f}

Evaluate:
1. Is the information sufficient to answer the query comprehensively?
2. Are there gaps or aspects not covered?

Respond in JSON format:
{{
    "continue": true/false,
    "reason": "explanation",
    "refined_query": "new search query if continue=true, otherwise original query",
    "confidence": 0.0-1.0
}}"""

        try:
            response = self.ai_handler.send_request(
                system_prompt="You are a search result evaluator. Analyze completeness of search results.",
                user_prompt=prompt,
                request_format="json"
            )
            
            if response:
                data = json.loads(response)
                return {
                    'continue': data.get('continue', False),
                    'reason': data.get('reason', ''),
                    'refined_query': data.get('refined_query', original_query),
                    'current_confidence': data.get('confidence', current_confidence)
                }
        except Exception as e:
            self.logger.warning(f"AI evaluation failed: {e}")
        
        # Fallback to heuristic
        return self._evaluate_need_more_data(original_query)
    
    def _create_refined_query(self, original_query: str) -> str:
        """
        Create a refined query for next iteration.
        
        Simple approach: add modifiers or related terms.
        For AI-powered refinement, use _ai_evaluate_need_more_data.
        """
        # Extract key terms from high-relevance sources
        high_relevance_sources = [
            s for s in self.aggregated_sources 
            if s['relevance'] >= 0.7
        ]
        
        if not high_relevance_sources:
            # Try with different query structure
            return f"{original_query} guide tutorial"
        
        # Look for common terms in titles
        all_words = []
        for source in high_relevance_sources:
            title_words = re.findall(r'\b\w{4,}\b', source['title'].lower())
            all_words.extend(title_words)
        
        # Find words not in original query
        query_words = set(original_query.lower().split())
        new_words = [w for w in all_words if w not in query_words]
        
        if new_words:
            # Add most common new word
            from collections import Counter
            common_word = Counter(new_words).most_common(1)[0][0]
            return f"{original_query} {common_word}"
        
        return original_query
    
    def _calculate_overall_confidence(self) -> float:
        """
        Calculate overall confidence based on aggregated sources.
        
        Returns:
            Confidence score (0.0 - 1.0)
        """
        if not self.aggregated_sources:
            return 0.0
        
        # Weight by relevance
        total_relevance = sum(s['relevance'] for s in self.aggregated_sources)
        
        # Consider number of sources
        source_factor = min(1.0, len(self.aggregated_sources) / 5)
        
        # Consider content depth
        avg_content_length = sum(
            len(s.get('content', '')) for s in self.aggregated_sources
        ) / len(self.aggregated_sources)
        content_factor = min(1.0, avg_content_length / 2000)
        
        # Combined confidence
        confidence = (
            (total_relevance / len(self.aggregated_sources)) * 0.5 +
            source_factor * 0.3 +
            content_factor * 0.2
        )
        
        return round(min(1.0, confidence), 2)
    
    def _build_response(self, success: bool, error: str = None) -> Dict[str, Any]:
        """
        Build final response dictionary.
        """
        if not success:
            return {
                'success': False,
                'summary': f"Search failed: {error}",
                'sources': [],
                'confidence': 0.0,
                'iterations_used': self.iteration_count,
                'follow_up_suggestions': []
            }
        
        # Sort sources by relevance
        sorted_sources = sorted(
            self.aggregated_sources,
            key=lambda x: x['relevance'],
            reverse=True
        )
        
        # Build summary
        summary = self._generate_summary(sorted_sources)
        
        # Generate follow-up suggestions
        follow_ups = self._generate_follow_ups(sorted_sources)
        
        # Clean sources for output (remove internal fields)
        clean_sources = []
        for source in sorted_sources:
            clean_sources.append({
                'url': source['url'],
                'title': source['title'],
                'snippet': source['snippet'][:300] + '...' if len(source['snippet']) > 300 else source['snippet'],
                'content': source.get('content', ''),
                'relevance': source['relevance'],
            })
        
        return {
            'success': True,
            'summary': summary,
            'sources': clean_sources,
            'confidence': self._calculate_overall_confidence(),
            'iterations_used': self.iteration_count,
            'follow_up_suggestions': follow_ups
        }
    
    def _generate_summary(self, sources: List[Dict]) -> str:
        """
        Generate summary from sources.
        
        If AI handler available, uses AI for intelligent summarization.
        """
        if not sources:
            return "No relevant sources found."
        
        if self.ai_handler:
            return self._ai_generate_summary(sources)
        
        # Simple summary
        top_sources = sources[:3]
        summary_parts = [f"Found {len(sources)} sources."]

        for i, source in enumerate(top_sources, 1):
            summary_parts.append(f"{i}. {source['title']} (relevance: {source['relevance']:.0%})")
        
        return '\n'.join(summary_parts)
    
    def _ai_generate_summary(self, sources: List[Dict]) -> str:
        """
        Use AI to generate intelligent summary.
        """
        # Get current date and time for context
        current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        sources_text = []
        for source in sources[:5]:
            content = source.get('content', source.get('snippet', ''))[:1000]
            sources_text.append(f"Source: {source['title']}\nURL: {source['url']}\nContent: {content}\n")
        
        prompt = f"""Current date and time: {current_datetime}

Summarize the key information from these search results:

{chr(10).join(sources_text)}

Provide a concise summary of the main findings (2-3 paragraphs)."""

        try:
            response = self.ai_handler.send_request(
                system_prompt="You are a helpful assistant that summarizes web search results.",
                user_prompt=prompt,
                request_format="text"
            )
            
            if response:
                return response
        except Exception as e:
            self.logger.warning(f"AI summarization failed: {e}")
        
        return self._generate_summary(sources)
    
    def _generate_follow_ups(self, sources: List[Dict]) -> List[str]:
        """
        Generate follow-up search suggestions.
        """
        suggestions = []
        
        # Extract common topics from sources
        all_titles = ' '.join(s['title'] for s in sources)
        
        # Common follow-up patterns
        patterns = [
            ('tutorial', f"{all_titles} - consider searching for 'tutorial' or 'guide'"),
            ('example', f"{all_titles} - consider searching for 'examples' or 'code samples'"),
            ('documentation', f"{all_titles} - consider official documentation"),
        ]
        
        for keyword, suggestion in patterns:
            if keyword.lower() not in all_titles.lower():
                suggestions.append(suggestion)
                if len(suggestions) >= 3:
                    break
        
        return suggestions[:3]


# Convenience function for direct usage
def web_search(query: str, engine: str = 'duckduckgo', **kwargs) -> Dict[str, Any]:
    """
    Convenience function for quick web search.
    
    Args:
        query: Search query
        engine: 'duckduckgo' or 'searxng'
        **kwargs: Additional arguments for WebSearchAgent
        
    Returns:
        Search results dictionary
    """
    agent = WebSearchAgent()
    return agent.execute(query, engine=engine, **kwargs)