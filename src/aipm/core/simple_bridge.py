"""
Simplified Queue Bridge for AIPM

Works directly with CTRM database and LM Studio without Node.js dependency.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx


@dataclass
class PromptResult:
    """Result of a processed prompt."""
    success: bool
    content: Optional[str]
    provider: Optional[str]
    error: Optional[str]
    wait_time_ms: int = 0


class SimpleQueueBridge:
    """
    Simplified queue bridge that works with CTRM and LM Studio.
    
    No Node.js required.
    """
    
    def __init__(
        self,
        lm_studio_url: str = "http://localhost:1234",
        default_model: str = "local-model",
        timeout: float = 120.0,
    ):
        self.lm_studio_url = lm_studio_url
        self.default_model = default_model
        self.timeout = timeout
        self._client = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client
    
    async def is_available(self) -> bool:
        """Check if LM Studio is available."""
        try:
            client = await self._get_client()
            response = await client.get(f"{self.lm_studio_url}/v1/models")
            return response.status_code == 200
        except:
            return False
    
    async def process_prompt(
        self,
        prompt: str,
        model: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> PromptResult:
        """Process a prompt through LM Studio."""
        start_time = datetime.now()
        
        try:
            client = await self._get_client()
            
            response = await client.post(
                f"{self.lm_studio_url}/v1/completions",
                json={
                    "model": model or self.default_model,
                    "prompt": prompt,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
            )
            
            if response.status_code != 200:
                return PromptResult(
                    success=False,
                    content=None,
                    provider="lm_studio",
                    error=f"HTTP {response.status_code}: {response.text}",
                )
            
            data = response.json()
            content = data["choices"][0].get("text", "")
            
            elapsed = (datetime.now() - start_time).total_seconds() * 1000
            
            return PromptResult(
                success=True,
                content=content,
                provider="lm_studio",
                error=None,
                wait_time_ms=int(elapsed),
            )
        
        except Exception as e:
            return PromptResult(
                success=False,
                content=None,
                provider="lm_studio",
                error=str(e),
            )
    
    async def process_chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> PromptResult:
        """Process a chat-style prompt through LM Studio."""
        start_time = datetime.now()
        
        try:
            client = await self._get_client()
            
            response = await client.post(
                f"{self.lm_studio_url}/v1/chat/completions",
                json={
                    "model": model or self.default_model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
            )
            
            if response.status_code != 200:
                return PromptResult(
                    success=False,
                    content=None,
                    provider="lm_studio",
                    error=f"HTTP {response.status_code}: {response.text}",
                )
            
            data = response.json()
            content = data["choices"][0]["message"].get("content", "")
            
            elapsed = (datetime.now() - start_time).total_seconds() * 1000
            
            return PromptResult(
                success=True,
                content=content,
                provider="lm_studio",
                error=None,
                wait_time_ms=int(elapsed),
            )
        
        except Exception as e:
            return PromptResult(
                success=False,
                content=None,
                provider="lm_studio",
                error=str(e),
            )
    
    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


# Synchronous wrapper for convenience
class SyncQueueBridge:
    """Synchronous wrapper for SimpleQueueBridge."""
    
    def __init__(self, **kwargs):
        self._async_bridge = SimpleQueueBridge(**kwargs)
    
    def process_prompt(self, prompt: str, **kwargs) -> PromptResult:
        """Process a prompt synchronously."""
        return asyncio.run(self._async_bridge.process_prompt(prompt, **kwargs))
    
    def is_available(self) -> bool:
        """Check if LM Studio is available."""
        return asyncio.run(self._async_bridge.is_available())
