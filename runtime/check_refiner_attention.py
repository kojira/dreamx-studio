"""Tiny CPU contract tests and optional guarded CUDA smoke; no model weights."""
import argparse,ast,types,torch
p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('--cuda',action='store_true');a=p.parse_args()
with open(a.source) as f:tree=ast.parse(f.read())
fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='flash_attention')
ns={'torch':torch,'FLASH_ATTN_2_AVAILABLE':False,'FLASH_ATTN_3_AVAILABLE':False}
exec(compile(ast.Module(body=[fn],type_ignores=[]),a.source,'exec'),ns)
f=ns['flash_attention'];q=torch.ones((1,4,2,128),dtype=torch.bfloat16)
class CudaDispatchProbe:
    device=types.SimpleNamespace(type='cuda')
    dtype=q.dtype
    def size(self,*args):return q.size(*args)
    def transpose(self,*args):return q.transpose(*args)
    def flatten(self,*args):return q.flatten(*args)
probe=CudaDispatchProbe();out=f(probe,q,q)
assert out.shape==q.shape and torch.isfinite(out).all()
assert torch.allclose(out,q)
for option in [{'q_lens':[4]},{'k_lens':[4]},{'q_scale':2.0},{'softmax_scale':0.2},{'causal':True},{'window_size':(1,1)},{'dropout_p':0.1},{'deterministic':True},{'version':2}]:
    try:f(probe,q,q,**option)
    except RuntimeError as e:assert 'Unsupported options' in str(e)
    else:raise AssertionError('Unsupported option accepted')
calls=[]
def fa2(**kwargs):calls.append(True);return kwargs['q']
ns['FLASH_ATTN_2_AVAILABLE']=True;ns['flash_attn']=types.SimpleNamespace(flash_attn_varlen_func=fa2)
assert f(probe,q,q).shape==q.shape and calls
ns['FLASH_ATTN_2_AVAILABLE']=False
print('CPU_FALLBACK_CONTRACT_OK',flush=True)
if a.cuda:
    g=torch.ones((1,32,2,128),device='cuda',dtype=torch.bfloat16)
    result=f(g,g,g);torch.cuda.synchronize()
    assert result.shape==g.shape and torch.isfinite(result).all().item()
    assert torch.allclose(result,g)
    print('CUDA_FALLBACK_SMOKE_OK',flush=True)
