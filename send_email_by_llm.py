# 参考https://platform.openai.com/docs/guides/function-calling?api-mode=responses&example=send-email

import os
import json
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from openai import OpenAI
from config import OPENAI_API_KEY, LINKAI_API_KEY, SMTP_SERVER, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("email_bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("email_bot")


# 测试SMTP连接
def test_smtp_connection():
    """测试SMTP服务器连接"""
    smtp_server = SMTP_SERVER
    smtp_port = int(SMTP_PORT)
    smtp_username = SMTP_USERNAME
    smtp_password = SMTP_PASSWORD
    
    logger.info(f"测试SMTP连接: {smtp_server}:{smtp_port}")
    
    try:
        server = smtplib.SMTP(smtp_server, smtp_port, timeout=10)
        server.set_debuglevel(1)  # 启用SMTP调试
        server.starttls()
        
        logger.info("尝试登录...")
        server.login(smtp_username, smtp_password)
        logger.info("SMTP登录成功!")
        
        server.quit()
        return True
    except Exception as e:
        logger.error(f"SMTP连接测试失败: {str(e)}")
        if "Authentication" in str(e):
            logger.error("认证失败 - 如果使用Gmail，请检查是否启用了'应用专用密码'")
        return False

# 邮件发送函数
def send_email(to, subject, body):
    """
    发送电子邮件的函数
    
    参数:
        to (str): 收件人邮箱地址
        subject (str): 邮件主题
        body (str): 邮件正文内容
    
    返回:
        str: 成功或失败的消息
    """

    # 邮件服务器配置
    smtp_server = SMTP_SERVER
    smtp_port = int(SMTP_PORT)
    smtp_username = SMTP_USERNAME
    smtp_password = SMTP_PASSWORD
    
    # 发件人邮箱
    from_email = smtp_username
    
    logger.info(f"准备发送邮件到: {to}")
    logger.info(f"邮件主题: {subject}")
    logger.debug(f"邮件内容: {body[:100]}...")  # 只记录邮件内容的前100个字符
    
    # 创建邮件
    msg = MIMEMultipart()
    msg['From'] = from_email
    msg['To'] = to
    msg['Subject'] = subject
    
    # 添加邮件正文
    msg.attach(MIMEText(body, 'plain'))
    
    try:
        # 连接到SMTP服务器
        logger.info(f"连接到SMTP服务器: {smtp_server}:{smtp_port}")
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.set_debuglevel(1)  # 启用SMTP调试
        
        logger.info("启用TLS加密...")
        server.starttls()
        
        logger.info("尝试登录...")
        server.login(smtp_username, smtp_password)
        
        # 发送邮件
        logger.info("发送邮件...")
        server.send_message(msg)
        server.quit()
        logger.info(f"成功发送邮件到 {to}")
        return f"成功发送邮件到 {to}"
    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"SMTP认证失败: {str(e)}")
        return f"邮件发送失败: SMTP认证错误。如果使用Gmail，请确保使用'应用专用密码'而不是普通密码。"
    except smtplib.SMTPRecipientsRefused as e:
        logger.error(f"收件人被拒绝: {str(e)}")
        return f"邮件发送失败: 收件人地址无效或被拒绝。"
    except smtplib.SMTPSenderRefused as e:
        logger.error(f"发件人被拒绝: {str(e)}")
        return f"邮件发送失败: 发件人地址被拒绝。"
    except smtplib.SMTPDataError as e:
        logger.error(f"SMTP数据错误: {str(e)}")
        return f"邮件发送失败: SMTP数据错误，可能是内容被拒绝。"
    except smtplib.SMTPConnectError as e:
        logger.error(f"SMTP连接错误: {str(e)}")
        return f"邮件发送失败: 无法连接到SMTP服务器。"
    except smtplib.SMTPServerDisconnected as e:
        logger.error(f"SMTP服务器断开连接: {str(e)}")
        return f"邮件发送失败: 与SMTP服务器的连接意外断开。"
    except smtplib.SMTPResponseException as e:
        logger.error(f"SMTP响应异常: 代码 {e.smtp_code}, 错误: {e.smtp_error}")
        return f"邮件发送失败: SMTP服务器返回错误代码 {e.smtp_code}"
    except Exception as e:
        logger.error(f"发送邮件时发生未知错误: {str(e)}")
        return f"邮件发送失败: {str(e)}"

# 定义Function Calling的函数模式
tools = [{
    "type": "function",
    "name": "send_email",
    "description": "Send an email to a given recipient with a subject and message.",
    "parameters": {
        "type": "object",
        "properties": {
            "to": {
                "type": "string",
                "description": "The recipient email address."
            },
            "subject": {
                "type": "string",
                "description": "Email subject line."
            },
            "body": {
                "type": "string",
                "description": "Body of the email message."
            }
        },
        "required": ["to", "subject", "body"],
        "additionalProperties": False
    },
    "strict": True
}]

# 串联
def process_user_request(user_message, mode):
    """处理用户请求，调用OpenAI API并处理function calling结果"""
    logger.info("收到用户请求")
    logger.debug(f"用户消息: {user_message}")
    

    # 调用模型
    try:
        # 第一次调用API，让模型决定是否调用函数
        logger.info("调用语言模型API...")

        if mode == "OPENAI":
            # DIFFERENCE 1: 初始化OpenAI客户端
            client = OpenAI(api_key=OPENAI_API_KEY)

            input_messages = [{"role": "user", "content": user_message}]

            # OPENAI 官方文档中的响应生成方式
            # DIFFERENCE 2: 生成response的方式
            response = client.responses.create(
                model="gpt-4.1-nano",
                input=[{"role": "user", "content": "Can you send an email to ilan@example.com and katia@example.com saying hi?"}],
                tools=tools
            )

            if response.output and len(response.output) > 0 and response.output[0].type == "function_call":
                # 获取函数调用信息
                tool_call = response.output[0]
                function_name = tool_call.name
                args = json.loads(tool_call.arguments)

                # 执行函数 - 这里是发送邮件
                if function_name == "send_email":
                    result = send_email(args.get("to"), args.get("subject"), args.get("body"))
                else:
                    result = "未知函数"
                
                # 将结果返回给模型以获取最终响应
                input_messages.append(tool_call)  # 添加模型的函数调用消息
                input_messages.append({
                    "type": "function_call_output",
                    "call_id": tool_call.call_id,
                    "output": result
                })
                
                final_response = client.responses.create(
                    model="gpt-4.1",  # 或其他支持function calling的模型
                    input=input_messages,
                    tools=tools,
                )
                
                return final_response.output_text
            else:
                # 如果模型没有调用函数，直接返回响应
                return response.output_text if hasattr(response, 'output_text') else "无响应"


        elif mode == "LINKAI":
            # DIFFERENCE 1: 使用代理API创建客户端
            client = OpenAI(
                api_key=LINKAI_API_KEY,
                base_url="https://api.link-ai.chat/v1"
            )
                        
            
            # 准备消息
            messages = []
            
            system_prompt = "You are an email assistant. When a user requests to send an email, you should always use the send_email function to send the email, rather than just providing the email content. Directly call the function instead of suggesting that the user manually copy and paste."

            # 添加系统提示
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
                logger.debug("添加了系统提示")
            
            # 添加用户消息
            messages.append({"role": "user", "content": user_message})

            # Difference 2: 生成response
            # Failed！无法成功调用tools，可能是client.chat.completions或使用代理的原因？
            response = client.chat.completions.create(
                model="gpt-4.1-nano",  # 使用代理支持的模型
                messages=messages,
                tools=tools,
                tool_choice="auto"  # 让模型决定是否调用函数
            )
            logger.info("收到API响应")
            

            print("条件一是否满足", bool(response.choices))
            print("条件二是否满足", bool(hasattr(response.choices[0], 'message')))
            print("条件三是否满足", bool(hasattr(response.choices[0].message, 'tool_calls')))
            print("条件四是否满足", bool(response.choices[0].message.tool_calls))

            # 检查响应中是否包含函数调用
            if response.choices and hasattr(response.choices[0], 'message') and hasattr(response.choices[0].message, 'tool_calls') and response.choices[0].message.tool_calls:
                # 获取函数调用
                tool_calls = response.choices[0].message.tool_calls
                logger.info(f"模型请求调用函数，发现 {len(tool_calls)} 个工具调用")
                
                # 将助手的回复添加到消息历史
                messages.append({
                    "role": "assistant",
                    "content": response.choices[0].message.content or "",
                    "tool_calls": tool_calls
                })
                
                # 执行所有函数调用并添加结果
                for tool_call in tool_calls:
                    function_name = tool_call.function.name
                    logger.info(f"处理函数调用: {function_name}")
                    
                    try:
                        function_args = json.loads(tool_call.function.arguments)
                        logger.debug(f"函数参数: {json.dumps(function_args)}")
                        
                        # 执行函数
                        if function_name == "send_email":
                            logger.info("开始发送邮件...")
                            result = send_email(
                                function_args.get("to"),
                                function_args.get("subject"),
                                function_args.get("body")
                            )
                        else:
                            result = f"未知函数: {function_name}"
                            logger.warning(f"尝试调用未知函数: {function_name}")
                        
                        logger.info(f"函数执行结果: {result}")
                    except json.JSONDecodeError as e:
                        result = f"解析函数参数时出错: {str(e)}"
                        logger.error(f"解析函数参数时出错: {str(e)}")
                    except Exception as e:
                        result = f"执行函数时出错: {str(e)}"
                        logger.error(f"执行函数时出错: {str(e)}")
                    
                    # 添加函数结果到消息
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result
                    })
                
                # 第二次调用API，让模型根据函数结果生成最终回复
                logger.info("再次调用API以处理函数结果...")
                final_response = client.chat.completions.create(
                    model="gpt-4.1-nano",
                    messages=messages
                )
                
                logger.info("处理完成，返回最终响应")
                return final_response.choices[0].message.content
            else:
                # 如果没有函数调用，直接返回模型的回复
                logger.info("模型未请求调用函数，直接返回响应")
                return response.choices[0].message.content
    
    except Exception as e:
        logger.error(f"处理请求时出错: {str(e)}")
        return f"处理请求时出错: {str(e)}"






# 使用示例
if __name__ == "__main__":
    # 测试SMTP连接
    logger.info("程序启动，首先测试SMTP连接")
    if not test_smtp_connection():
        logger.error("SMTP连接测试失败，请检查配置后再试")
        print("SMTP连接测试失败，请检查配置后再试")

    
    # 测试用户消息
    user_message = "请你生成一份中式口味的每日食谱，并作为邮件内容发送给shicrazy1997@gmail.com"
    
    # 处理请求
    logger.info("开始处理用户请求")
    result = process_user_request(user_message, mode="LINKAI")
    logger.info(f"处理结果: {result}")
    print("处理结果:", result)