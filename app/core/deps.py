from fastapi import Header


async def get_api_key(x_api_key: str = Header(default="anonymous")) -> str:
    return x_api_key