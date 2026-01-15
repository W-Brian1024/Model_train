import torch
from transformers import (
    AutoModelForCausalLM, 
    AutoTokenizer,
    BitsAndBytesConfig
)
from accelerate import infer_auto_device_map, init_empty_weights
import logging

logger = logging.getLogger(__name__)

class ModelLoader:
    def __init__(self):
        self.model = None
        self.tokenizer = None
        
    def load_model(self, model_path, load_in_8bit=True, device_map="auto"):
        """智能加载模型，支持 8-bit 量化"""
        try:
            # 配置 8-bit 量化
            if load_in_8bit:
                quantization_config = BitsAndBytesConfig(
                    load_in_8bit=True,
                    llm_int8_enable_fp32_cpu_offload=True
                )
            else:
                quantization_config = None
            
            # 加载 tokenizer
            logger.info(f"Loading tokenizer from {model_path}")
            self.tokenizer = AutoTokenizer.from_pretrained(
                model_path,
                trust_remote_code=True,
                padding_side='left'
            )
            
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token
            
            # 加载模型
            logger.info(f"Loading model with 8bit={load_in_8bit}, device_map={device_map}")
            self.model = AutoModelForCausalLM.from_pretrained(
                model_path,
                quantization_config=quantization_config,
                device_map=device_map,
                torch_dtype=torch.float16 if not load_in_8bit else None,
                trust_remote_code=True,
                low_cpu_mem_usage=True
            )
            
            logger.info("Model loaded successfully!")
            return True
            
        except Exception as e:
            logger.error(f"Error loading model: {str(e)}")
            return False
    
    def get_memory_usage(self):
        """获取 GPU 内存使用情况"""
        if torch.cuda.is_available():
            return {
                f"gpu_{i}": f"{torch.cuda.memory_allocated(i) / 1024**3:.2f}GB / {torch.cuda.memory_reserved(i) / 1024**3:.2f}GB"
                for i in range(torch.cuda.device_count())
            }
        return {"gpu": "not available"}