"""
智能体管理 API

提供智能体的启用、禁用、删除、重载等管理功能
"""

from fastapi import APIRouter, HTTPException
from pathlib import Path
from typing import Dict, Any
import shutil
import yaml

from app.agents.registry import AgentRegistry
from app.agents.loader import AgentLoader

router = APIRouter(prefix="/api/v1/agent-management", tags=["agent-management"])


def get_agents_dir() -> Path:
    """获取智能体目录"""
    return Path(__file__).parent.parent.parent / "agents"


def get_agent_info(agent_dir: Path) -> Dict[str, Any]:
    """获取智能体信息
    
    Args:
        agent_dir: 智能体目录
        
    Returns:
        智能体信息字典
    """
    config_file = agent_dir / "agent.yaml"
    
    if not config_file.exists():
        return None
    
    with open(config_file, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # 检查是否已加载到注册中心
    agent_name = config.get('name', '')
    is_loaded = agent_name in AgentRegistry.list_agents()
    
    return {
        "name": config.get('name', ''),
        "version": config.get('version', ''),
        "description": config.get('description', ''),
        "author": config.get('author', ''),
        "enabled": config.get('enabled', True),
        "is_loaded": is_loaded,
        "entry_class": config.get('entry_class', ''),
        "dependencies": config.get('dependencies', []),
        "has_requirements": (agent_dir / "requirements.txt").exists(),
        "directory": agent_dir.name
    }


@router.get("/agents")
async def list_all_agents():
    """列出所有智能体（包括已启用和已禁用的）
    
    Returns:
        智能体列表
    """
    agents_dir = get_agents_dir()
    agents = []
    
    for item in agents_dir.iterdir():
        if item.is_dir() and not item.name.startswith('_'):
            agent_info = get_agent_info(item)
            if agent_info:
                agents.append(agent_info)
    
    return {
        "total": len(agents),
        "agents": agents
    }


@router.get("/agents/{agent_name}")
async def get_agent_detail(agent_name: str):
    """获取智能体详细信息
    
    Args:
        agent_name: 智能体目录名
    """
    agents_dir = get_agents_dir()
    agent_dir = agents_dir / agent_name
    
    if not agent_dir.exists():
        raise HTTPException(status_code=404, detail=f"智能体不存在: {agent_name}")
    
    agent_info = get_agent_info(agent_dir)
    
    if not agent_info:
        raise HTTPException(status_code=404, detail="智能体配置文件不存在")
    
    # 读取 requirements.txt
    requirements = []
    req_file = agent_dir / "requirements.txt"
    if req_file.exists():
        with open(req_file, 'r', encoding='utf-8') as f:
            requirements = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    
    # 读取 README.md
    readme = None
    readme_file = agent_dir / "README.md"
    if readme_file.exists():
        with open(readme_file, 'r', encoding='utf-8') as f:
            readme = f.read()
    
    # 统计文件
    prompts = []
    prompts_dir = agent_dir / "prompts"
    if prompts_dir.exists():
        prompts = [f.name for f in prompts_dir.iterdir() if f.is_file()]
    
    schemas = []
    schemas_dir = agent_dir / "schemas"
    if schemas_dir.exists():
        schemas = [f.name for f in schemas_dir.iterdir() if f.is_file() and f.name.endswith('.py')]
    
    services = []
    services_dir = agent_dir / "services"
    if services_dir.exists():
        services = [f.name for f in services_dir.iterdir() if f.is_file() and f.name.endswith('.py')]
    
    return {
        **agent_info,
        "requirements": requirements,
        "readme": readme,
        "files": {
            "prompts": prompts,
            "schemas": schemas,
            "services": services
        }
    }


@router.post("/agents/{agent_name}/enable")
async def enable_agent(agent_name: str):
    """启用智能体
    
    Args:
        agent_name: 智能体目录名
    """
    agents_dir = get_agents_dir()
    agent_dir = agents_dir / agent_name
    
    if not agent_dir.exists():
        raise HTTPException(status_code=404, detail=f"智能体不存在: {agent_name}")
    
    config_file = agent_dir / "agent.yaml"
    if not config_file.exists():
        raise HTTPException(status_code=404, detail="智能体配置文件不存在")
    
    # 读取配置
    with open(config_file, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # 修改 enabled 字段
    config['enabled'] = True
    
    # 写回配置
    with open(config_file, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, allow_unicode=True)
    
    return {
        "success": True,
        "message": f"智能体 {agent_name} 已启用",
        "note": "需要重新加载才能生效"
    }


@router.post("/agents/{agent_name}/disable")
async def disable_agent(agent_name: str):
    """禁用智能体
    
    Args:
        agent_name: 智能体目录名
    """
    agents_dir = get_agents_dir()
    agent_dir = agents_dir / agent_name
    
    if not agent_dir.exists():
        raise HTTPException(status_code=404, detail=f"智能体不存在: {agent_name}")
    
    config_file = agent_dir / "agent.yaml"
    if not config_file.exists():
        raise HTTPException(status_code=404, detail="智能体配置文件不存在")
    
    # 读取配置
    with open(config_file, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # 修改 enabled 字段
    config['enabled'] = False
    
    # 写回配置
    with open(config_file, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, allow_unicode=True)
    
    return {
        "success": True,
        "message": f"智能体 {agent_name} 已禁用",
        "note": "需要重新加载才能生效"
    }


@router.delete("/agents/{agent_name}")
async def delete_agent(agent_name: str):
    """删除智能体
    
    Args:
        agent_name: 智能体目录名
    """
    agents_dir = get_agents_dir()
    agent_dir = agents_dir / agent_name
    
    if not agent_dir.exists():
        raise HTTPException(status_code=404, detail=f"智能体不存在: {agent_name}")
    
    # 获取智能体信息
    agent_info = get_agent_info(agent_dir)
    
    # 删除目录
    shutil.rmtree(agent_dir)
    
    return {
        "success": True,
        "message": f"智能体 {agent_name} 已删除",
        "deleted_agent": agent_info,
        "note": "需要重新加载才能从注册中心移除"
    }


@router.post("/reload")
async def reload_agents():
    """重新加载所有智能体
    
    警告：这会清空注册中心并重新加载所有智能体
    
    Returns:
        重新加载结果
    """
    try:
        # 清空注册中心
        AgentRegistry.clear()
        
        # 重新加载所有智能体
        AgentLoader.load_all_agents()
        
        # 获取已加载的智能体
        loaded_agents = AgentRegistry.list_agents()
        
        return {
            "success": True,
            "message": "智能体重新加载成功",
            "loaded_count": len(loaded_agents),
            "agents": [
                {"name": name, "description": desc}
                for name, desc in loaded_agents.items()
            ]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重新加载失败: {str(e)}")


@router.get("/health")
async def health_check():
    """健康检查"""
    agents_dir = get_agents_dir()
    loaded_agents = AgentRegistry.list_agents()
    
    return {
        "status": "healthy",
        "agents_directory": str(agents_dir),
        "loaded_agents_count": len(loaded_agents)
    }

