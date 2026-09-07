"""Tiny CUDA/BF16/SDPA compatibility probe; never loads model weights."""
import json
import platform
import torch
import torchvision
import torchaudio
import transformers
import diffusers
import torch.nn.functional as F

assert platform.machine() == 'aarch64', 'Expected ARM64 target'
assert torch.__version__.split('+')[0] == '2.10.0'
assert torchvision.__version__.split('+')[0] == '0.25.0'
assert torchaudio.__version__.split('+')[0] == '2.10.0'
assert torch.cuda.is_available(), 'CUDA unavailable'
assert torch.cuda.is_bf16_supported(), 'BF16 unsupported'
with torch.inference_mode():
    q = torch.randn(1, 2, 16, 64, device='cuda', dtype=torch.bfloat16)
    result = F.scaled_dot_product_attention(q, q, q)
    torch.cuda.synchronize()
    assert torch.isfinite(result).all().item()
    # SDPA alone did not expose mixed cuBLAS/cuBLASLt versions on the base image.
    x=torch.ones((512,4096),device='cuda',dtype=torch.bfloat16)
    w=torch.ones((4096,4096),device='cuda',dtype=torch.bfloat16)
    y=F.linear(x,w)
    torch.cuda.synchronize()
    assert torch.isfinite(y).all().item()
print(json.dumps({'architecture':platform.machine(),'torch':torch.__version__,
                  'torchvision':torchvision.__version__,'torchaudio':torchaudio.__version__,
                  'transformers':transformers.__version__,'diffusers':diffusers.__version__,
                  'cuda':torch.version.cuda,'device':torch.cuda.get_device_name(),
                  'capability':torch.cuda.get_device_capability(),
                  'tiny_bf16_sdpa':'passed','bf16_linear':'passed','allocated_bytes':torch.cuda.memory_allocated()}))
