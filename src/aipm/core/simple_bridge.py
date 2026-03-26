"""
Simplified Queue Bridge for AIPM

Works directly with CTRM database and LM Studio without Node.js dependency.
Includes model loading/unloading capabilities.
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


@dataclass
class ModelInfo:
    """Information about a model."""
    key: str
    display_name: str
    publisher: str
    architecture: str
    quantization: str
    is_loaded: bool
    context_length: int


class SimpleQueueBridge:
    """
    Simplified queue bridge that works with CTRM and LM Studio.
    
    Features:
    - List available models
    - Load/unload models
    - Process prompts via completions or chat API
    - No Node.js required
    """
    
    def __init__(
        self,
        lm_studio_url: str = "http://localhost:1234",
        default_model: str = "qwen/qwen3.5-9b",
        timeout: float = 120.0,
    ):
        self.lm_studio_url = lm_studio_url
        self.default_model = default_model
        self.timeout = timeout
        self._client = None
        self._loaded_model = None
    
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
    
    # === Model Management ===
    
    async def list_models(self) -> List[ModelInfo]:
        """List all available models."""
        try:
            client = await self._get_client()
            response = await client.get(f"{self.lm_studio_url}/api/v1/models")
            
            if response.status_code != 200:
                return []
            
            data = response.json()
            models = []
            
            for m in data.get("models", []):
                # Check if model is loaded via loaded_instances
                loaded_instances = m.get("loaded_instances", [])
                is_loaded = len(loaded_instances) > 0
                
                quant = m.get("quantization", {})
                if isinstance(quant, dict):
                    quant_name = quant.get("name", "unknown")
                else:
                    quant_name = str(quant)
                
                models.append(ModelInfo(
                    key=m.get("key", "unknown"),
                    display_name=m.get("display_name", "Unknown"),
                    publisher=m.get("publisher", "unknown"),
                    architecture=m.get("architecture", "unknown"),
                    quantization=quant_name,
                    is_loaded=is_loaded,
                    context_length=m.get("max_context_length", 4096),
                ))
            
            return models
        
        except Exception as e:
            print(f"Error listing models: {e}")
            return []
    
    async def get_loaded_model(self) -> Optional[str]:
        """Get the currently loaded model."""
        models = await self.list_models()
        for m in models:
            if m.is_loaded:
                return m.key
        return None
    
    async def load_model(self, model_key: str) -> Dict[str, Any]:
        """
        Load a model.
        
        Returns:
            {"success": bool, "message": str}
        """
        try:
            client = await self._get_client()
            response = await client.post(
                f"{self.lm_studio_url}/api/v1/models/load",
                json={"model": model_key},
            )
            
            if response.status_code == 200:
                self._loaded_model = model_key
                return {"success": True, "message": f"Loaded {model_key}"}
            else:
                error = response.json().get("error", {})
                error_msg = error.get("message", f"Failed to load {model_key}")
                
                # Check for common errors and provide guidance
                if "Utility process" in error_msg:
                    error_msg = (
                        f"LM Studio cannot load model via API. "
                        f"Please load '{model_key}' manually in LM Studio GUI, "
                        f"or install the lms CLI: 'npm install -g lmstudio-cli'"
                    )
                
                return {
                    "success": False,
                    "message": error_msg,
                }
        
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    async def unload_model(self, model_key: str) -> Dict[str, Any]:
        """
        Unload a model.
        
        Note: LM Studio requires instance_id for unloading.
        This may not work in all cases.
        """
        try:
            client = await self._get_client()
            response = await client.post(
                f"{self.lm_studio_url}/api/v1/models/unload",
                json={"model": model_key},
            )
            
            if response.status_code == 200:
                if self._loaded_model == model_key:
                    self._loaded_model = None
                return {"success": True, "message": f"Unloaded {model_key}"}
            else:
                error = response.json().get("error", {})
                return {
                    "success": False,
                    "message": error.get("message", f"Failed to unload {model_key}"),
                }
        
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    async def ensure_model_loaded(self, model_key: str) -> bool:
        """
        Ensure a model is loaded, loading it if necessary.
        
        Returns:
            True if model is loaded, False otherwise
        """
        # Check if already loaded
        loaded = await self.get_loaded_model()
        if loaded == model_key:
            return True
        
        # Try to load
        result = await self.load_model(model_key)
        return result["success"]
    
    # === Prompt Processing ===
    
    async def process_prompt(
        self,
        prompt: str,
        model: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        auto_load: bool = True,
    ) -> PromptResult:
        """Process a prompt through LM Studio."""
        start_time = datetime.now()
        model = model or self.default_model
        
        try:
            client = await self._get_client()
            
            # Optionally ensure model is loaded
            if auto_load:
                await self.ensure_model_loaded(model)
            
            response = await client.post(
                f"{self.lm_studio_url}/v1/completions",
                json={
                    "model": model,
                    "prompt": prompt,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
            )
            
            if response.status_code != 200:
                error_text = response.text
                return PromptResult(
                    success=False,
                    content=None,
                    provider="lm_studio",
                    error=f"HTTP {response.status_code}: {error_text}",
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
        auto_load: bool = True,
    ) -> PromptResult:
        """Process a chat-style prompt through LM Studio."""
        start_time = datetime.now()
        model = model or self.default_model
        
        try:
            client = await self._get_client()
            
            # Optionally ensure model is loaded
            if auto_load:
                await self.ensure_model_loaded(model)
            
            response = await client.post(
                f"{self.lm_studio_url}/v1/chat/completions",
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
            )
            
            if response.status_code != 200:
                error_text = response.text
                return PromptResult(
                    success=False,
                    content=None,
                    provider="lm_studio",
                    error=f"HTTP {response.status_code}: {error_text}",
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
    
    def process_chat(self, messages: List[Dict[str, str]], **kwargs) -> PromptResult:
        """Process chat messages synchronously."""
        return asyncio.run(self._async_bridge.process_chat(messages, **kwargs))
    
    def is_available(self) -> bool:
        """Check if LM Studio is available."""
        return asyncio.run(self._async_bridge.is_available())
    
    def list_models(self) -> List[ModelInfo]:
        """List all available models."""
        return asyncio.run(self._async_bridge.list_models())
    
    def load_model(self, model_key: str) -> Dict[str, Any]:
        """Load a model."""
        return asyncio.run(self._async_bridge.load_model(model_key))
    
    def unload_model(self, model_key: str) -> Dict[str, Any]:
        """Unload a model."""
        return asyncio.run(self._async_bridge.unload_model(model_key))
    
    def get_loaded_model(self) -> Optional[str]:
        """Get the currently loaded model."""
        return asyncio.run(self._async_bridge.get_loaded_model())
