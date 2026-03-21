import asyncio
import gc
from typing import List, Literal, Optional, overload

from llama_cpp import Iterator, Llama
from llama_cpp.llama_types import (
    ChatCompletionRequestMessage,
    CreateChatCompletionResponse,
    CreateChatCompletionStreamResponse,
)


class AgentService:
    """
    Handles the lifecycle and operations of the Small Language Models (SLM).
    Optimized for 4GB VRAM hardware with dynamic layer offloading.
    """

    def __init__(self):
        self.model: Optional[Llama] = None
        self.current_model_path: Optional[str] = None

    async def load(
        self,
        path: str,
        n_ctx: int,
        n_gpu_layers: int = 50,
    ) -> None:
        """
        Loads an SLM model with dynamic hardware constraints.

        Args:
            path: Path to the .gguf file.
            n_gpu_layers: Number of layers to offload to GPU.
            n_ctx: Context window size.
        """
        # Bypass I/O if the model is already in VRAM
        if self.current_model_path == path and self.model is not None:
            return

        self.model = await asyncio.to_thread(
            Llama,
            model_path=path,
            n_gpu_layers=n_gpu_layers,
            n_ctx=n_ctx,
            flash_attn=True,  # Critical for Gemma 3 / Phi memory efficiency
            verbose=False,
        )

        self.current_model_path = path
        print(
            f"Model loaded successfully: {path} (Layers: {n_gpu_layers}, Context: {n_ctx})"
        )

    async def unload(self) -> None:
        """
        Force-releases VRAM and synchronizes deallocation.
        """
        if self.model is not None:
            del self.model
            self.model = None
            self.current_model_path = None

            # Flush Python objects and wait for CUDA driver to unmap memory
            await asyncio.to_thread(gc.collect)
            await asyncio.sleep(0.5)

    async def swap(
        self,
        path: str,
        n_ctx: int,
        n_gpu_layers: int = 50,
    ) -> None:
        """
        Swaps models, only triggering unload if a different model is requested.
        """
        if self.current_model_path == path:
            return

        await self.unload()
        await self.load(path=path, n_gpu_layers=n_gpu_layers, n_ctx=n_ctx)

    @overload
    async def generate(
        self,
        messages: List[ChatCompletionRequestMessage],
        temp: float,
        max_tokens: int,
        stream: Literal[False] = False,
    ) -> CreateChatCompletionResponse: ...

    @overload
    async def generate(
        self,
        messages: List[ChatCompletionRequestMessage],
        temp: float,
        max_tokens: int,
        stream: Literal[True],
    ) -> Iterator[CreateChatCompletionStreamResponse]: ...

    async def generate(
        self,
        messages: List[ChatCompletionRequestMessage],
        temp: float,
        max_tokens: int,
        stream: bool = False,
    ) -> CreateChatCompletionResponse | Iterator[CreateChatCompletionStreamResponse]:
        """
        Generates completions with repetition penalty to prevent infinite loops.
        """
        if self.model is None:
            raise ValueError("Model not loaded")

        response = await asyncio.to_thread(
            self.model.create_chat_completion,
            messages=messages,
            temperature=temp,
            repeat_penalty=1.15,
            stream=stream,
            max_tokens=max_tokens,
        )

        return response
