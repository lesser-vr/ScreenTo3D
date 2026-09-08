"""Export-only standard matmul attention, preserving upstream mask/upcast rules.

Reference idea: MapMindAI/DepthAnythingOnnx (MIT), converter at commit
693f8eda3caaf0c453bc96a3e4ef7a5e653f5d19. Independently implemented for the
three-dimensional upstream streaming attention path, not its 4D CPU fallback.
"""
import types
import torch


def plain_attention(self, query, key, value, attention_mask=None):
    q = query.float() if self.upcast_attention else query
    k = key.float() if self.upcast_attention else key
    logits = torch.matmul(q, k.transpose(-1, -2)) * self.scale
    if attention_mask is not None:
        logits = logits + attention_mask
    if self.upcast_softmax:
        logits = logits.float()
    weights = torch.softmax(logits, dim=-1).to(value.dtype)
    return self.reshape_batch_dim_to_heads(torch.matmul(weights, value))


def install(model):
    count = 0
    for module in model.modules():
        if module.__class__.__module__.endswith('motion_module.motion_module') or module.__class__.__module__.endswith('motion_module.attention'):
            if callable(getattr(module, '_attention', None)):
                module._attention = types.MethodType(plain_attention, module)
                count += 1
    if count != 8:
        raise RuntimeError(f'Unexpected temporal attention count: {count}')
    return count
