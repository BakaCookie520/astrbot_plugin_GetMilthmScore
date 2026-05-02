from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from astrbot.api import AstrBotConfig
import os
import aiohttp
import json
import asyncio
import base64
from typing import Dict, Optional, List

BASE_URL = "https://api.mhtl.im"

@register("Milthm 成绩查询", "BakaCookie520", "集成 milthm 平台的成绩查询插件", "1.0.0")
class MilthmPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.plugin_dir = os.path.dirname(__file__)
        self.config = config
        self.data_file = os.path.join(self.plugin_dir, "user_data.json")
        self.user_data: Dict[str, Dict] = self._load_user_data()

    def _load_user_data(self) -> Dict:
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载用户数据失败: {e}")
        return {}

    def _save_user_data(self):
        try:
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump(self.user_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存用户数据失败: {e}")

    async def initialize(self):
        """异步初始化"""

    async def _api_request(self, method: str, path: str, data: Optional[Dict] = None, params: Optional[Dict] = None) -> Optional[Dict]:
        """通用 API 请求"""
        url = f"{BASE_URL}{path}"
        headers = {
            "Content-Type": "application/json",
            "Origin": "https://nya.mhtl.im",
            "Referer": "https://nya.mhtl.im/"
        }
        logger.info(f"发起 API 请求: {method} {url}, params: {params}, data: {data}")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method=method,
                    url=url,
                    json=data,
                    params=params,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"API 请求成功: {result}")
                        return result
                    else:
                        error_text = await response.text()
                        logger.error(f"API 请求失败: {url}, 状态码: {response.status}, 响应: {error_text}")
                        return None
        except Exception as e:
            logger.error(f"API 请求异常: {e}")
            return None

    async def _save_user_info(self, user_id: str, username: str, details: Dict):
        """保存用户信息"""
        logger.info(f"保存用户信息 - user_id: {user_id}, username: {username}, details: {details}")
        token = details.get("login_token")
        uid = details.get("uid")
        
        self.user_data[user_id] = {
            "username": username,
            "token": token,
            "uid": uid,
            "authorized": False
        }
        self._save_user_data()
        logger.info(f"已保存用户数据: {self.user_data[user_id]}")
        
        return token, uid

    @filter.command("milthm_register")
    async def register_user(self, event: AstrMessageEvent, username: str, password: str):
        """注册 Milthm 账号"""
        user_id = event.message_obj.sender.user_id
        yield event.plain_result(f"正在注册账号 `{username}`...")

        response = await self._api_request(
            "POST",
            "/_u/register",
            {"username": username, "password": password}
        )

        if response and response.get("result") == "200":
            details = response.get("details", {})
            token, uid = await self._save_user_info(user_id, username, details)
            
            yield event.plain_result(
                f"注册成功！\n"
                f"用户名: {username}\n"
                f"UID: {uid}\n\n"
                f"正在获取 milkloud 授权链接..."
            )

            auth_url = await self._get_auth_url(username, token)
            if auth_url:
                yield event.plain_result(
                    f"请点击下方链接完成 milkloud 授权：\n{auth_url}\n\n"
                    f"授权完成后，使用 `/milthm_query` 查询成绩！"
                )
            else:
                yield event.plain_result(
                    f"获取授权链接失败，请稍后使用 `/milthm_auth` 重新获取。"
                )
        else:
            msg = response.get("message", "未知错误") if response else "请求失败"
            yield event.plain_result(f"注册失败: {msg}")

    @filter.command("milthm_login")
    async def login_user(self, event: AstrMessageEvent, username: str, password: str):
        """登录 Milthm 账号"""
        user_id = event.message_obj.sender.user_id
        yield event.plain_result(f"正在登录账号 `{username}`...")

        response = await self._api_request(
            "POST",
            f"/_u/{username}/login",
            {"password": password}
        )

        if response and response.get("result") == "200":
            details = response.get("details", {})
            token, uid = await self._save_user_info(user_id, username, details)
            
            yield event.plain_result(
                f"登录成功！\n"
                f"用户名: {username}\n"
                f"UID: {uid}\n\n"
                f"正在获取 milkloud 授权链接..."
            )

            auth_url = await self._get_auth_url(username, token)
            if auth_url:
                yield event.plain_result(
                    f"请点击下方链接完成 milkloud 授权：\n{auth_url}\n\n"
                    f"授权完成后，使用 `/milthm_query` 查询成绩！"
                )
            else:
                yield event.plain_result(
                    f"获取授权链接失败，请稍后使用 `/milthm_auth` 重新获取。"
                )
        else:
            msg = response.get("message", "未知错误") if response else "请求失败"
            yield event.plain_result(f"登录失败: {msg}")

    @filter.command("milthm_auth")
    async def get_auth(self, event: AstrMessageEvent):
        """获取 milkloud 授权链接"""
        user_id = event.message_obj.sender.user_id
        if user_id not in self.user_data:
            yield event.plain_result("请先使用 `/milthm_register` 或 `/milthm_login` 登录！")
            return

        user_info = self.user_data[user_id]
        username = user_info["username"]
        token = user_info["token"]

        yield event.plain_result("正在获取授权链接...")

        auth_url = await self._get_auth_url(username, token)
        if auth_url:
            yield event.plain_result(
                f"请点击下方链接完成 milkloud 授权：\n{auth_url}\n\n"
                f"授权完成后，使用 `/milthm_query` 查询成绩"
            )
        else:
            yield event.plain_result("获取授权链接失败，请稍后再试")

    async def _get_auth_url(self, username: str, token: str) -> Optional[str]:
        """获取授权链接"""
        response = await self._api_request(
            "GET",
            f"/_m/gen/{username}",
            params={"token": token}
        )
        if response and response.get("result") == "200":
            details = response.get("details", {})
            return details.get("url")
        return None

    @filter.command("milthm_query")
    async def query_score(self, event: AstrMessageEvent):
        """查询成绩图片"""
        user_id = event.message_obj.sender.user_id
        logger.info(f"用户 {user_id} 发起查询请求")
        if user_id not in self.user_data:
            yield event.plain_result("请先使用 `/milthm_register` 或 `/milthm_login` 登录！")
            return

        user_info = self.user_data[user_id]
        username = user_info["username"]
        token = user_info["token"]
        logger.info(f"用户信息 - username: {username}, token: {token}")

        yield event.plain_result("正在发起成绩查询任务...")

        task_response = await self._api_request(
            "POST",
            f"/_t/{username}",
            params={"token": token},
            data={}
        )

        if not task_response:
            yield event.plain_result("发起查询任务失败！")
            return

        max_attempts = 30
        for i in range(max_attempts):
            await asyncio.sleep(2)
            result_list = await self._get_result_list(username, token)
            if not result_list:
                continue

            image_result = None
            for result in result_list:
                if result.get("type") == "image":
                    image_result = result
                    break

            if image_result:
                result_id = image_result["result_id"]
                yield event.plain_result("查询成功！正在获取图片...")

                image_data = await self._get_result_image(username, result_id, token)
                if image_data:
                    temp_image = os.path.join(self.plugin_dir, f"temp_{user_id}.png")
                    try:
                        with open(temp_image, "wb") as f:
                            f.write(image_data)
                        yield event.image_result(temp_image)
                    finally:
                        if os.path.exists(temp_image):
                            try:
                                os.remove(temp_image)
                            except:
                                pass
                else:
                    yield event.plain_result("获取图片失败！")
                return

            if (i + 1) % 5 == 0:
                yield event.plain_result(f"正在处理中... ({i + 1}/{max_attempts})")

        yield event.plain_result("查询超时，请稍后再试")

    async def _get_result_list(self, username: str, token: str) -> Optional[List]:
        """获取结果列表"""
        response = await self._api_request(
            "GET",
            f"/_r/{username}",
            params={"token": token}
        )
        if response and response.get("result") == "200":
            return response.get("details", [])
        return None

    async def _get_result_image(self, username: str, result_id: int, token: str) -> Optional[bytes]:
        """获取结果图片"""
        response = await self._api_request(
            "GET",
            f"/_r/{username}/{result_id}",
            params={"token": token}
        )
        if response and response.get("result") == "200":
            details = response.get("details", {})
            extra = details.get("extra")
            if extra:
                try:
                    return base64.b64decode(extra)
                except Exception as e:
                    logger.error(f"解码图片失败: {e}")
        return None

    @filter.command("milthm_status")
    async def check_status(self, event: AstrMessageEvent):
        """检查账号状态"""
        user_id = event.message_obj.sender.user_id
        if user_id not in self.user_data:
            yield event.plain_result("未绑定账号")
            return

        user_info = self.user_data[user_id]
        username = user_info["username"]
        token = user_info["token"]

        profile = await self._api_request(
            "GET",
            f"/_u/{username}/profile",
            params={"token": token}
        )

        milk_status = await self._api_request(
            "GET",
            f"/_u/{username}/milkloud-status",
            params={"token": token}
        )

        status_msg = f"账号状态:\n"
        status_msg += f"用户名: {username}\n"

        if profile and profile.get("result") == "200":
            details = profile.get("details", {})
            status_msg += f"UID: {details.get('uid', 'N/A')}\n"

        if milk_status and milk_status.get("result") == "200":
            details = milk_status.get("details", {})
            if details.get("code"):
                status_msg += "milkloud: 已授权"
            else:
                status_msg += "milkloud: 未授权"
        else:
            status_msg += "milkloud: 状态未知"

        yield event.plain_result(status_msg)

    @filter.command("milthm_help")
    async def help_command(self, event: AstrMessageEvent):
        """帮助信息"""
        help_text = """Milthm 成绩查询插件帮助

/milthm_register <用户名> <密码> - 注册新账号
/milthm_login <用户名> <密码> - 登录已有账号
/milthm_auth - 获取 milkloud 授权链接
/milthm_query - 查询成绩图片
/milthm_status - 检查账号状态
/milthm_help - 显示帮助信息

使用说明：
1. 注册新用户使用 `/milthm_register <用户名> <密码>`
2. 登录已有账号使用 `/milthm_login <用户名> <密码>`
3. 点击机器人发送的授权链接完成 milkloud 授权
4. 使用 `/milthm_query` 查询成绩
"""
        yield event.plain_result(help_text)

    async def terminate(self):
        """插件销毁"""
