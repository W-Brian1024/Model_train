# # qwen_fastapi/main.py

# from fastapi import FastAPI, HTTPException
# from pydantic import BaseModel

# app = FastAPI()

# # 健康检查路由
# @app.get("/health")
# def health_check():
#     return {"status": "healthy"}

# # Qwen 模型调用示例路由
# class QwenRequest(BaseModel):
#     prompt: str

# @app.post("/qwen")
# def qwen_response(request: QwenRequest):
#     # 示例：返回固定响应（实际应调用 Qwen 模型）
#     return {"response": f"Qwen received: {request.prompt}"}

# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8000)

import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from transformers import AutoTokenizer, AutoModelForCausalLM

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# 健康检查路由
@app.get("/health")
def health_check():
    logger.info("Health check requested")
    return {"status": "healthy"}

# Qwen 模型调用示例路由
class QwenRequest(BaseModel):
    prompt: str

@app.post("/qwen")
def qwen_response(request: QwenRequest):
    logger.info(f"Received prompt: {request.prompt}")
    
    # 检查输入是否为空
    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty")
    
    # 加载模型和分词器
    try:
        tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen-7B")
        model = AutoModelForCausalLM.from_pretrained("Qwen/Qwen-7B")
    except Exception as e:
        logger.error(f"Failed to load model: {e}")
        raise HTTPException(status_code=500, detail="Failed to load model")
    
    # 处理输入
    inputs = tokenizer(request.prompt, return_tensors="pt")
    
    # 生成响应
    try:
        outputs = model.generate(**inputs, max_length=100)
        response = tokenizer.decode(outputs[0], skip_special_tokens=True)
    except Exception as e:
        logger.error(f"Failed to generate response: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate response")
    
    logger.info("Model response generated")
    return {"response": response}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)