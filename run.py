import uvicorn
from app.core.config import settings


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.uvicorn_reload,  # 生产环境应关闭
        log_level="info",
        workers= settings.uvicorn_workers,  # 根据 CPU 核心数调整，建议设置成CPU核心数或者+1
        loop="asyncio"
    )